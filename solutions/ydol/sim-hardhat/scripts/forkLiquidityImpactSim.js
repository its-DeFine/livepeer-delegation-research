import { network } from "hardhat";

let ethers;

const DEFAULTS = {
  pool: "0x4fD47e5102DFBF95541F64ED6FE13d4eD26D2546", // LPT/WETH Uni v3 0.30% on Arbitrum
  quoter: "0xb27308f9F90D607463bb33eA1BeBb41C27CE5AB6", // Uni v3 Quoter v1
  positionManager: "0xC36442b4a4522E871399CD717aBDD847Ab11FE88",
  token0: "0x289ba1701C2F088cf0faf8B3705246331cB8A839", // LPT
  token1: "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1", // WETH
  fee: 3000,
  lptUsd: 3.13,
  ethUsd: 2975.33,
  tradeUsd: [1000, 5000, 10000, 25000, 50000],
  totalUsd: 782000, // ~250k LPT @ $3.13, split 50/50 for a “mature” state
  rangeMult: 20, // tickSpacing multiples on each side
  out: null,
};

const ABIS = {
  erc20: [
    "function balanceOf(address) view returns (uint256)",
    "function approve(address,uint256) returns (bool)",
    "function decimals() view returns (uint8)",
  ],
  weth: ["function deposit() payable"],
  pool: [
    "function slot0() view returns (uint160 sqrtPriceX96,int24 tick,uint16,uint16,uint16,uint8,bool)",
    "function tickSpacing() view returns (int24)",
  ],
  quoter: [
    "function quoteExactInputSingle(address,address,uint24,uint256,uint160) returns (uint256)",
  ],
  positionManager: [
    "function mint((address token0,address token1,uint24 fee,int24 tickLower,int24 tickUpper,uint256 amount0Desired,uint256 amount1Desired,uint256 amount0Min,uint256 amount1Min,address recipient,uint256 deadline)) returns (uint256 tokenId,uint128 liquidity,uint256 amount0,uint256 amount1)",
  ],
};

function parseArgsFromEnv() {
  const out = { ...DEFAULTS };

  if (process.env.SIM_OUT) out.out = process.env.SIM_OUT;
  if (process.env.SIM_LPT_USD) out.lptUsd = Number(process.env.SIM_LPT_USD);
  if (process.env.SIM_ETH_USD) out.ethUsd = Number(process.env.SIM_ETH_USD);
  if (process.env.SIM_TOTAL_USD) out.totalUsd = Number(process.env.SIM_TOTAL_USD);
  if (process.env.SIM_RANGE_MULT) out.rangeMult = Number(process.env.SIM_RANGE_MULT);
  if (process.env.SIM_TRADE_USD) {
    out.tradeUsd = process.env.SIM_TRADE_USD.split(",")
      .map((x) => Number(x.trim()))
      .filter((x) => Number.isFinite(x));
  }

  return out;
}

function sqrtPriceX96ToPriceToken1PerToken0(sqrtPriceX96) {
  // price = (sqrtPriceX96 / 2^96)^2 in raw token units
  const Q96 = 2n ** 96n;
  const sp = sqrtPriceX96;
  // Use bigint fixed-point: (sp^2 / Q96^2) with 1e18 scaling.
  const num = sp * sp * 10n ** 18n;
  const den = Q96 * Q96;
  return Number(num / den) / 1e18;
}

async function findBalanceSlot(token, holder, expectedBalance) {
  const provider = ethers.provider;
  const coder = ethers.AbiCoder.defaultAbiCoder();
  for (let slot = 0n; slot < 50n; slot++) {
    const key = ethers.keccak256(coder.encode(["address", "uint256"], [holder, slot]));
    const raw = await provider.send("eth_getStorageAt", [token, key, "latest"]);
    const bal = BigInt(raw);
    if (bal === expectedBalance) {
      return slot;
    }
  }
  throw new Error("Could not find balance mapping slot (searched 0..49)");
}

async function setErc20Balance(token, account, amount, hintHolder) {
  const provider = ethers.provider;
  const erc20 = new ethers.Contract(token, ABIS.erc20, provider);
  const holder = hintHolder;
  const expected = await erc20.balanceOf(holder);
  const slot = await findBalanceSlot(token, holder, expected);
  const coder = ethers.AbiCoder.defaultAbiCoder();
  const key = ethers.keccak256(coder.encode(["address", "uint256"], [account, slot]));
  const value = ethers.zeroPadValue(ethers.toBeHex(amount), 32);
  await provider.send("hardhat_setStorageAt", [token, key, value]);
}

async function quoteSlippage({ quoter, token0, token1, fee, lptUsd, ethUsd, tradeUsd, spotPrice }) {
  const q = new ethers.Contract(quoter, ABIS.quoter, ethers.provider);
  const rows = [];
  for (const usd of tradeUsd) {
    const wethIn = usd / ethUsd;
    const lptIn = usd / lptUsd;

    const amountInWeth = ethers.parseUnits(wethIn.toFixed(18), 18);
    const lptOut = await q.quoteExactInputSingle.staticCall(token1, token0, fee, amountInWeth, 0);
    const lptOutF = Number(ethers.formatUnits(lptOut, 18));
    const execBuy = wethIn / lptOutF;
    const buyImpactPct = (execBuy / spotPrice - 1) * 100;

    const amountInLpt = ethers.parseUnits(lptIn.toFixed(18), 18);
    const wethOut = await q.quoteExactInputSingle.staticCall(token0, token1, fee, amountInLpt, 0);
    const wethOutF = Number(ethers.formatUnits(wethOut, 18));
    const execSell = wethOutF / lptIn;
    const sellImpactPct = (1 - execSell / spotPrice) * 100;

    rows.push({
      usd,
      buyImpactPct,
      sellImpactPct,
      buyLptOut: lptOutF,
      sellWethOut: wethOutF,
    });
  }
  return rows;
}

async function main() {
  const args = parseArgsFromEnv();

  ({ ethers } = await network.connect());

  const [signer] = await ethers.getSigners();
  const me = await signer.getAddress();

  const pool = new ethers.Contract(args.pool, ABIS.pool, ethers.provider);
  const slot0 = await pool.slot0();
  const sqrtPriceX96 = slot0[0];
  const tick = Number(slot0[1]);
  const tickSpacing = Number(await pool.tickSpacing());
  const spot = sqrtPriceX96ToPriceToken1PerToken0(sqrtPriceX96);

  console.log(`Fork @ pool=${args.pool}`);
  console.log(`tick=${tick} tickSpacing=${tickSpacing} spot(WETH/LPT)=${spot}`);

  const before = await quoteSlippage({
    quoter: args.quoter,
    token0: args.token0,
    token1: args.token1,
    fee: args.fee,
    lptUsd: args.lptUsd,
    ethUsd: args.ethUsd,
    tradeUsd: args.tradeUsd,
    spotPrice: spot,
  });

  // Add 50/50 liquidity around the current tick.
  const halfUsd = args.totalUsd / 2;
  const lptAmount = halfUsd / args.lptUsd;
  const wethAmount = halfUsd / args.ethUsd;
  const lptUnits = ethers.parseUnits(lptAmount.toFixed(18), 18);
  const wethUnits = ethers.parseUnits(wethAmount.toFixed(18), 18);

  const weth = new ethers.Contract(args.token1, ABIS.weth, signer);
  await (await weth.deposit({ value: wethUnits })).wait();

  // Use the pool itself as a guaranteed non-zero LPT holder to locate the balance mapping slot.
  await setErc20Balance(args.token0, me, lptUnits, args.pool);

  const token0 = new ethers.Contract(args.token0, ABIS.erc20, signer);
  const token1 = new ethers.Contract(args.token1, ABIS.erc20, signer);
  await (await token0.approve(args.positionManager, lptUnits)).wait();
  await (await token1.approve(args.positionManager, wethUnits)).wait();

  const pm = new ethers.Contract(args.positionManager, ABIS.positionManager, signer);

  const lower = Math.floor((tick - args.rangeMult * tickSpacing) / tickSpacing) * tickSpacing;
  const upper = Math.ceil((tick + args.rangeMult * tickSpacing) / tickSpacing) * tickSpacing;

  const deadline = Math.floor(Date.now() / 1000) + 3600;
  const mintParams = {
    token0: args.token0,
    token1: args.token1,
    fee: args.fee,
    tickLower: lower,
    tickUpper: upper,
    amount0Desired: lptUnits,
    amount1Desired: wethUnits,
    amount0Min: 0,
    amount1Min: 0,
    recipient: me,
    deadline,
  };

  const mintTx = await pm.mint(mintParams);
  const receipt = await mintTx.wait();
  const mintEv = receipt.logs?.find(() => true);
  void mintEv;

  // Re-read spot after mint.
  const slot0After = await pool.slot0();
  const spotAfter = sqrtPriceX96ToPriceToken1PerToken0(slot0After[0]);

  const after = await quoteSlippage({
    quoter: args.quoter,
    token0: args.token0,
    token1: args.token1,
    fee: args.fee,
    lptUsd: args.lptUsd,
    ethUsd: args.ethUsd,
    tradeUsd: args.tradeUsd,
    spotPrice: spotAfter,
  });

  const result = {
    meta: {
      pool: args.pool,
      quoter: args.quoter,
      positionManager: args.positionManager,
      token0: args.token0,
      token1: args.token1,
      fee: args.fee,
      lptUsd: args.lptUsd,
      ethUsd: args.ethUsd,
      totalUsd: args.totalUsd,
      rangeMult: args.rangeMult,
      tickBefore: tick,
      tickAfter: Number(slot0After[1]),
      tickSpacing,
      spotBefore: spot,
      spotAfter,
      tickLower: lower,
      tickUpper: upper,
    },
    before,
    after,
  };

  console.log("\nUSD\tBuyImpact(before→after)\tSellImpact(before→after)");
  for (let i = 0; i < result.before.length; i++) {
    const b = result.before[i];
    const a = result.after[i];
    console.log(
      `${b.usd}\t${b.buyImpactPct.toFixed(2)}%→${a.buyImpactPct.toFixed(2)}%\t\t${b.sellImpactPct.toFixed(2)}%→${a.sellImpactPct.toFixed(2)}%`
    );
  }

  if (args.out) {
    const fs = await import("node:fs/promises");
    await fs.writeFile(args.out, JSON.stringify(result, null, 2), "utf-8");
    console.log(`\nWrote ${args.out}`);
  }
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
