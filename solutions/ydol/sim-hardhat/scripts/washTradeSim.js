import { network } from "hardhat";

function fmt(ethers, x) {
  return Number(ethers.formatEther(x)).toFixed(6);
}

async function deployBase(ethers, { feeBps, managerFeeBps, rewardPerUnit }) {
  const [deployer, dao, manager] = await ethers.getSigners();

  const Token = await ethers.getContractFactory("MintableERC20");
  const FeeCollector = await ethers.getContractFactory("FeeCollector");
  const Rewarder = await ethers.getContractFactory("Rewarder");
  const AMM = await ethers.getContractFactory("SimpleCPAMM");

  const token0 = await Token.deploy("Token0", "T0", 18, deployer.address);
  await token0.waitForDeployment();
  const token1 = await Token.deploy("Token1", "T1", 18, deployer.address);
  await token1.waitForDeployment();
  const rewardToken = await Token.deploy("Reward", "RWD", 18, deployer.address);
  await rewardToken.waitForDeployment();

  const rewarder = await Rewarder.deploy(await rewardToken.getAddress(), deployer.address);
  await rewarder.waitForDeployment();
  await rewardToken.transferOwnership(await rewarder.getAddress());
  await rewarder.setRewardPerUnit(rewardPerUnit);

  const feeCollector = await FeeCollector.deploy(dao.address, manager.address, managerFeeBps);
  await feeCollector.waitForDeployment();

  const amm = await AMM.deploy(await token0.getAddress(), await token1.getAddress(), feeBps, await feeCollector.getAddress(), await rewarder.getAddress());
  await amm.waitForDeployment();

  // Seed balances
  await token0.mint(dao.address, ethers.parseEther("500000"));
  await token1.mint(dao.address, ethers.parseEther("500000"));
  await token0.mint(manager.address, ethers.parseEther("100000"));

  // Provide liquidity (DAO owns pool; fees split by FeeCollector)
  await token0.connect(dao).approve(await amm.getAddress(), ethers.MaxUint256);
  await token1.connect(dao).approve(await amm.getAddress(), ethers.MaxUint256);
  await amm.connect(dao).addLiquidity(ethers.parseEther("500000"), ethers.parseEther("500000"));

  await token0.connect(manager).approve(await amm.getAddress(), ethers.MaxUint256);
  await token1.connect(manager).approve(await amm.getAddress(), ethers.MaxUint256);

  return { deployer, dao, manager, token0, token1, rewardToken, rewarder, feeCollector, amm };
}

async function runWashTrade(ethers, { rounds, amount0InPerRound, feeBps, managerFeeBps, rewardPerUnit }) {
  const env = await deployBase(ethers, { feeBps, managerFeeBps, rewardPerUnit });
  const { dao, manager, token0, token1, rewardToken, feeCollector, amm } = env;

  const t0 = await token0.getAddress();
  const t1 = await token1.getAddress();

  const start0 = await token0.balanceOf(manager.address);
  const start1 = await token1.balanceOf(manager.address);
  const startR = await rewardToken.balanceOf(manager.address);
  const startValue = start0 + start1 + startR;

  let totalVolume = 0n;

  for (let i = 0; i < rounds; i++) {
    const out1 = await amm.connect(manager).swap0For1.staticCall(amount0InPerRound);
    await amm.connect(manager).swap0For1(amount0InPerRound);
    totalVolume += amount0InPerRound;

    const out0 = await amm.connect(manager).swap1For0.staticCall(out1);
    await amm.connect(manager).swap1For0(out1);
    totalVolume += out1;

    // Keep the simulation stable: stop if manager runs out.
    const cur0 = await token0.balanceOf(manager.address);
    if (cur0 < amount0InPerRound) break;
  }

  // Split fees to DAO + manager (manager is paid in fees even if net PnL is negative)
  await feeCollector.distribute(t0);
  await feeCollector.distribute(t1);

  const end0 = await token0.balanceOf(manager.address);
  const end1 = await token1.balanceOf(manager.address);
  const endR = await rewardToken.balanceOf(manager.address);
  const endValue = end0 + end1 + endR;

  const daoFee0 = await token0.balanceOf(dao.address);
  const daoFee1 = await token1.balanceOf(dao.address);

  return {
    feeBps,
    managerFeeBps,
    rewardPerUnit,
    rounds,
    amount0InPerRound,
    totalVolume,
    start: { t0: start0, t1: start1, rwd: startR, value: startValue },
    end: { t0: end0, t1: end1, rwd: endR, value: endValue },
    daoFeeBalances: { t0: daoFee0, t1: daoFee1 },
  };
}

async function main() {
  const { ethers } = await network.connect();
  const rounds = 50;
  const amount0InPerRound = ethers.parseEther("1000");

  const feeBps = 30; // 0.30%
  const managerFeeBps = 5000; // 50% of fees

  console.log("Scenario A: no external rewards (wash trading should lose)\n");
  const base = await runWashTrade(ethers, { rounds, amount0InPerRound, feeBps, managerFeeBps, rewardPerUnit: 0n });
  const loss = base.start.value - base.end.value;
  console.log(`totalVolume: ${fmt(ethers, base.totalVolume)} (token units)`);
  console.log(
    `start value: ${fmt(ethers, base.start.value)} | end value: ${fmt(ethers, base.end.value)} | loss: ${fmt(ethers, loss)}`
  );
  console.log(
    `manager end balances: t0=${fmt(ethers, base.end.t0)} t1=${fmt(ethers, base.end.t1)} rwd=${fmt(ethers, base.end.rwd)}`
  );
  console.log(`dao fee balances: t0=${fmt(ethers, base.daoFeeBalances.t0)} t1=${fmt(ethers, base.daoFeeBalances.t1)}`);

  // Break-even rewardPerUnit (reward token valued at 1 unit of token0/token1 in this toy model)
  const breakevenRewardPerUnit = loss > 0n ? (loss * 10n ** 18n) / base.totalVolume : 0n;

  console.log("\nScenario B: external volume rewards at break-even rate\n");
  console.log(`breakevenRewardPerUnit: ${breakevenRewardPerUnit.toString()} (reward tokens per 1e18 of amountIn)`);
  const withReward = await runWashTrade(ethers, {
    rounds,
    amount0InPerRound,
    feeBps,
    managerFeeBps,
    rewardPerUnit: breakevenRewardPerUnit,
  });
  const loss2 = withReward.start.value - withReward.end.value;
  console.log(`totalVolume: ${fmt(ethers, withReward.totalVolume)}`);
  console.log(
    `start value: ${fmt(ethers, withReward.start.value)} | end value: ${fmt(ethers, withReward.end.value)} | net: ${fmt(ethers, loss2)}`
  );
  console.log(
    `manager end balances: t0=${fmt(ethers, withReward.end.t0)} t1=${fmt(ethers, withReward.end.t1)} rwd=${fmt(ethers, withReward.end.rwd)}`
  );
  console.log(
    `dao fee balances: t0=${fmt(ethers, withReward.daoFeeBalances.t0)} t1=${fmt(ethers, withReward.daoFeeBalances.t1)}`
  );
}

main().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
