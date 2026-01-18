# Post 5 — @Arrakis

Created: 2025-12-09T11:18:38.424Z

Thanks for your comments
@vires-in-numeris
A few clarifications from our side regarding the points above:


Negative IL should be minimal here, largely because the position starts with 100% LPT inventory. The strategy is designed so that the pool gradually builds ETH exposure over time through fees and natural order flow, rather than taking immediate directional IL risk or causing any active sell pressure.


Arrakis runs some of the most advanced LP management strategies in the industry, with a focus on combining capital efficiency with risk management. The objective is to sustain capital in the long term. The strategies are actively managed and maintained by our in-house quant team.


Regarding backtesting: simulating active LP strategies on historic data is inherently limited. Outcomes won’t accurately reflect future performance because (1) active LP strategies change the shape of the pool as they operate, (2) competitor LPs / on-chain trade volume react in real time, and (3) the bootstrapping nature of this strategy—which starts 100% LPT and accumulates ETH over time— is not clearly replicable on historic data.


As for the 0.3% vs 1% pool: we chose the 0.3% tier because it is currently the deepest LPT/ETH pool on Uniswap, making it the most appropriate benchmark for evaluating and attributing impact during the Arrakis engagement. It also ensures comparability to the existing liquidity environment while reducing fragmentation during the bootstrap phase. If the community prefers, we can also adjust and deploy funds on a 1% fee tier LPT/ETH pool.
