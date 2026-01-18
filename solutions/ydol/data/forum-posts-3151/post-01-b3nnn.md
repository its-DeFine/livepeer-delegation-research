# Post 1 — @b3nnn

Created: 2025-12-01T01:17:30.267Z

TLDR


We propose to address known UX issues and ease and costs to participate by increasing DEX liquidity. Arrakis offers an optimal solution for our specific needs, and we are requesting 250,000 LPT for deployment to a Uniswap v4 pool which will significantly reduce slippage for ecosystem participants


Motivation


The Capital Markets Advisory board made improving onchain liquidity a tactical recommendation, specifically sighting:


Low liquidity levels on our DEX pools (primarily Uniswap on Arbitrum). This creates high slippage when trying to transact with any size, and might refrain larger stakeholders or participants from buying LPT


The much higher ratio of available liquidity on centralized exchanges compared to DEXs drives participants to rely on centralized platforms, exposing them to the inherent risks associated with centralized providers


Further, centralised exchanges often don’t support L2 withdrawals. This results in delayed bridging and withdrawal processing between L1 & L2, impairing overall UX and the efficiency of orchestrators as it relates to capital allocation


In short, improved L2 Dex liquidity is essential for both current and future participants in Livepeer.


Recommended Solution


How to address our challenges is relatively straightforward to describe:


Increase the amount of liquidity on targeted DEX pool/s


Ensure the solution is executing against this goal as agreed


Use funds wisely, ensuring a good balance between what we pay and what we receive


Any solution
will require liquidity from the on-chain treasury
to start bootstrapping an optimal asset mix. In addition to this liquidity requirement, using a traditional market maker is likely a major expense (in the range of $15-20K per month). While traditional market makers can do a good job in actively managing liquidity, especially on centralised exchanges, they often present new or additional challenges:


Market makers typically operate through asset loan agreements, using our capital to actively manage liquidity across venues. While this model provides flexibility and professional management, it can make visibility into how and where assets are deployed more challenging.


Compared to centralized venues, on-chain liquidity provision is often less economically attractive for market makers. As a result, they may prioritize other strategies or venues where returns are higher, which can limit incentives to deepen on-chain liquidity.


Ensuring that capital is being used effectively by traditional market makers remains challenging, as it requires clear visibility into capital deployment and a deep understanding of the alternative strategies they pursue.


While none of this is insurmountable, it requires significant thought, effort and time to ensure oversight and manage risk.


Arrakis pro is an ideal solution to addresses these challenges.


Arrakis specifically addresses each of these challenges because:


It is built specifically for managing onchain liquidity on DEXs


The assets are stored in a vault controlled by a multisig made up of Livpeer Foundation members. This means the treasury, via the Foundation, can withdraw and return the liquidity at any time


Because it is onchain, and through the features provided in Arrakis pro, we can check and confirm at any time where our assets are and what strategies are being applied.


It rebalances positions by setting up ranges / limit orders, no swaps involved. The solution algorithmically minimises price impact given the allocated capital and bootstraps base asset liquidity without causing negative selling pressure.


Arrakis leverages sophisticated algorithms to increase capital efficiency for the deployed capital and reduce slippage for traders on the DEX pools.


Arrakis vaults hold ~$170M TVL and the team actively manages the on-chain liquidity for over 100 protocols. Projects such as MakerDAO, Lido, Morpho, Gelato, Redstone, Wormhole, Across, Euler, Usual, Syrup,
Venice.ai
,
Ether.fi
, etc. are benefiting from the high capital efficiency and cost effectiveness for DEX liquidity optimization enabled by Arrakis PRO.


For more information regarding Arrakis and Arrakis Pro, feel free to have a look at their docs or join their community:


Arrakis
|
Twitter
|
Resources


In addition, the team are present here and will address any questions directly - hello
@Arrakis


The Ask


We want to significantly decrease slippage and costs for orchestrators and other participants to interact with the network through onchain liquidity.


We are asking for 250,000 LPT (approx. $1M in USD value) to be held in a multisig controlled by the Livepeer Foundation, to be deployed via an onchain vault with Arrakis as a concentrated pool on Uniswap v4.


Management of concentrated liquidity on Uniswap V4 allows for larger trades with minimal price impact, improving the overall trading experience. Savings to participants are substantial at approx. $1500 in slippage reduction on a $25,000 sale of LPT (estimate based on data below).


image
1358×482 54.2 KB


Comparison of current and estimated price impact (after successful ETH liquidity bootstrapping) for buying LPT and ETH across different amounts


Specification for Livepeer


The Arrakis team uses the existing LPT/ETH pool on the 0.3% fee tier for UniswapV4


Arrakis then deploys a dedicated vault managed by the Arrakis Pro smart contract for this LPT/ETH Uniswap pool.


The Livepeer Foundation team establish a ⅔ Multisig for custody of the funds. If the proposal passes, funds are transferred onchain to this multisig account


Through this Livepeer Foundation multisig, we deposit $1 million worth of $LPT into the Arrakis Pro vault.
Transfers in and out of the vault are controlled by the multisig, meaning they cannot be deployed or moved by Arrakis elsewhere


Arrakis Pro will allocate the provided liquidity in a concentrated and fully active market making strategy to facilitate trading on UniswapV4.


The strategy initially operates to bootstrap ETH to establish a 50/50 inventory ratio over the first months. The primary objective is to create price stability by generating deep liquidity and reaching an even inventory over time.


For the services provided, Arrakis charges the following fees:


Arrakis Asset-under-Management (AUM) fee:
1% per year, waived for the first 6 months


Arrakis performance fee:
50% of trading fees the vault generates


FAQ


What are the risks of this model?


Deploying funds to DEX pools bears smart contract risk and general market risk (e.g. token exposure, impermanent loss). Arrakis smart contracts have been audited by leading security firms and currently secure +$150M TVL (
https://docs.arrakis.finance/text/resources/audits.html
)


What happens to the capital required?


The capital required is deployed by the Livepeer DAO, via a Foundation controlled multisig, to a self-custodial smart contract vault and can be withdrawn at any point in time. Arrakis does not hold custody, nor control the funds deployed outside of the mandate to manage DEX liquidity on Uniswap V4 for the respective trading pair.


Will this impact the current liquidity on CEXs?


Arrakis mandate is to gradually improve on-chain markets and provide deeper liquidity for the respective pair over time on DEX markets. CEX markets will not be affected.


How does the Arrakis model differ from standard AMMs (like Uniswap v3)?


Arrakis provides a sophisticated on-chain market making service, running dedicated algorithmic market making strategies.


Instead of manually deploying funds into the CLAMM pool, Arrakis algorithmically rebalances the position and runs active liquidity management strategies.


Will our liquidity still be actively managed, or will it be passively allocated in a vault?


Close to 100% of the liquidity deployed with an Arrakis vault is actively deployed to the Uniswap CLAMM pool and provides liquidity. Small shares of liquidity remain in the vault as token reserves for rebalancing purposes.


How is the strategy for the vault determined — who sets the parameters, and how often are they rebalanced?


Arrakis quant team fine tunes the strategies and engages in period review cycles along with 24h-365day monitoring and alerting.


Who controls or can modify the AMM strategy parameters?


Arrakis strategies are designed, deployed and maintained by professional quant traders. The Foundation can be involved in discussion in regular intervals as needed to further align on achieving the stated goals.


Will the community have visibility into performance and strategy updates?


The Foundation delegates will receive access to a custom real time analytics dashboard and can share periodic updates to the forum for the community.


What happens to the liquidity if the vault underperforms or becomes unbalanced?


Liquidity is actively rebalanced towards a 50:50 ratio by placing one sided limit maker orders. In adverse market scenarios strategies will adjust to certain market volatility settings.


How do fees compare to centralized market makers?


Centralized market makers work in two models: a) Loan & Option b) Retainer Fix Fee payment. Arrakis works on a profit sharing of trading fees earned (50% captured by the Livepeer DAO, 50% retained by Arrakis for the services provided)


How will LP performance be measured?


LP performance will be measured by market depth, price impact, slippage improvement, total volumes facilitated.


What happens after funds are returned?


It’s important to note that the liquidity in the vault can remain deployed indefinitely, but also returned to the onchain treasury or control by the voters at any time. As funds will now be held in both ETH and LPT, the community can be involved in discussions about how returned funds are stored or used.


This is a large proportion of the current treasury. What gives?


We recognise that this is a large ask relative to the current size and value of the treasury. The size and value of the treasury will be addressed in a separate proposal. As it relates to this proposal, consider that we will reduce slippage costs by approx 2-3X
on every dex transaction
. The ROI on this proposal will be quite substantial.
