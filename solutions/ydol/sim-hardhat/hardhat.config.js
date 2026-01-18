import { defineConfig } from "hardhat/config";
import hardhatEthers from "@nomicfoundation/hardhat-ethers";

export default defineConfig({
  plugins: [hardhatEthers],
  chainDescriptors: {
    // Hardhat v3 treats Arbitrum as `generic` by default and requires a hardfork history.
    // For our fork-based Uni v3 simulations, treating Arbitrum as `l1` is sufficient.
    42161: {
      name: "Arbitrum One (sim)",
      chainType: "l1",
      hardforkHistory: {
        // Treat the fork as “latest hardfork” for all historical blocks we execute against.
        osaka: { blockNumber: 0 },
      },
    },
  },
  solidity: {
    version: "0.8.24",
    settings: {
      optimizer: { enabled: true, runs: 200 },
    },
  },
  networks: {
    hardhat: {
      type: "edr-simulated",
      forking: {
        url: process.env.ARBITRUM_RPC_URL ?? "https://arb1.arbitrum.io/rpc",
      },
    },
  },
});
