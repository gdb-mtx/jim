# Proprietary Quantitative Trading Partnership Proposal

## George Borshukov, January 2020

## Inspiration

The inspiration for the idea comes from recent books about 3 inspiring and financially successful individuals who share a common approach to the financial markets and money making. All 3 of them were hedge fund managers and practitioners (if you wish pioneers) of the "systematic", aka quantitative or algorithmic trading approach to financial market investing.

Ed Thorpe:
[A Man for All Markets: From Las Vegas to Wall Street, How I Beat the Dealer and the Market](https://www.amazon.com/Man-All-Markets-Street-Dealer/dp/B01N4JAXQM/ref=sr_1_1?crid=2GEWLONM7I4KZ&keywords=a+man+for+all+markets&qid=1578371916&s=books&sprefix=A+Man+for+all+%2Cstripbooks%2C225&sr=1-1)

Jim Simons:
[The Man Who Solved the Market: How Jim Simons Launched the Quant Revolution](https://www.amazon.com/Man-Who-Solved-Market-Revolution/dp/073521798X)

Larry Hite:
[The Rule: How I Beat the Odds in the Markets and in Life - and How You Can Too](https://www.amazon.com/Rule-Beat-Odds-Markets-Life/dp/B07Y5QV6CH/ref=sr_1_1?crid=K4I9OZXBLN6I&keywords=the+rule+larry+hite&qid=1578371990&s=audible&sprefix=The+Rule+larry%2Caudible%2C229&sr=1-1)

## Why Now

The approach, philosophy, and methods pioneered, described, and followed by these quant hedge fund innovators have recently been democratized with minimal barrier of entry thanks to online quantitative trading platforms and open source algorithmic trading systems such as quantconnect.com. These platforms also provide integration with low cost trading brokerages with access to a variety of financial markets and instruments worldwide. Some of them also provide risk management, slippage and trading cost models utilized by more powerful professional quantitative trading systems traditionally used by hedge funds. This allows for a fairly low barrier of entry for multi-disciplinary technical teams to practise this approach to financial markets trading w/o the need for expensive upfront and operational costs to create a hedge fund by raising funds from wealthy investors, institutions, or family offices traditionally required. The platforms offer not only back testing against available historical data sets but also paper testing (actually live trading simulation w/o putting actual money at risk) at minimal cost.

The idea is also attractive because it represents an opportunity for a passive income, not a "job". The team involved will be able to work from anywhere and not be tied to a schedule and office, etc. It will be intellectually stimulating with a potential upside.

In contrast to this idea, despite the lower barrier of entry thanks to the rise of cloud computing and cloud services, traditional technology startups have a huge challenge with product market fit. Even if the technology is innovative, inspiring, exciting to work on in order for it to result in a successful product and therefore financial success a market fit needs to be found.

With the idea described there is no such need. There isn't the complication of creating a traditional company, searching for a customer, business model, branding, website, voice, etc. or the politics and struggles and pressures that come with that. The goal is to find a way to make money by removing emotion from the process. Eliminate as much as possible the politics, committees, meetings, gossip and drama of a traditional company and in the process hopefully give a chance for the partners to improve their chances of financial freedom. The partnership is focused on lifestyle not the complications of running a company doing fundraising, sales, marketing, hiring required for a startup to be successful. It is more about the intellectual challenge and fun with a potential of financial upside if and when we decide to do actual live trading.

## Premise

The most valuable take away from the books referenced above is that markets are not completely efficient and still driven largely by human emotions and trends. Humans will be humans so there is still an opportunity. This opinion can of course be argued endlessly but that is not the point here. There are plenty of examples of successful quantitative trading (or systematic) approaches. The field was reserved for hedge funds started by wealthy individuals with access to even wealthier individuals. This is not the case anymore, the idea can be pursued as a side project, a hobby with upside. The main goal will be to limit the downside while allowing "unlimited" upside.

### Trading Horizon and Potential Simple Early Approach

We are not considering high frequency trading (HFT) which requires large computing power and proximity to exchanges and has increasingly become a less and less profitable frontier since the early 2010 when it exploded. Trading will be focused on daily, weekly or maximum monthly time horizons. The idea is to attempt to generate solid monthly double digit returns using any instrument. Stocks may be the hardest, so possibly explore trades in commodity futures, options, possibly even crypto. Instruments need to be diversified across many asset classes. A successful strategy outlined by Larry Hite is one of many bets with no single bet losing more than 2% of total capital. Key is to control the losses - limit losses but not the upside. Want to practice the idea of Asymmetric Leverage.

One simple method seen by the WealthSignals systems referenced below is to possibly use long and short (leveraged) versions of NASDAQ ETFs if we don't want to get into futures and options. That way a trend can be followed on both sides.

More sophisticated approaches will attempt to devise a trendfollowing technique based on Bayesian probabilities and Markov chains. These statistical techniques are commonly referenced as the foundation of some successful methods. We will not be trying to "invest" which is about knowing and having information that somehow we think or hope that other people in the market don't have. It will be more about following what other people are doing and knowing they will keep doing it and getting out in time as described by Larry Hite. Ray Dalio talks about an idea of 15 "uncorrelated" or least correlated bets. Find trends, follow the trends and exit at 2% (or X%) reversal.

### Why not Buy and Hold

Fundamental investing and stock picking requires a different skill and background. As far as index funds to make 5%-7% per year on your money you are risking 50% … that is an "awful trade" … there have been two distinct declines of 50% (Black swans - the dot com crash and the 2008 financial crisis) in 20 years, there are certainly more coming (such as the Covid-19 pandemic only 2 months after this document was created).

## Platforms

### Best Candidate

QuantConnect (www.quantconnect.com) still allows trading (can get immediately up and running but also has an open source LEAP API to run on our servers if needed). Has team and collaborative tools. It also offers back testing and paper trading at low cost so it appears to be the best platform based on research so far.

Second option less dependent on web interface can be Quantrocket.com

### Competition based

Quantiacs (www.quantiacs.com) is well respected but only allows competitions. Could be worth considering too as the prizes there are significant.

Quantopian (www.quantopian.com) is now mainly an educational tool and runs competitions. It stopped trading a couple years ago and had issues with users IP not being well protected

### Other

https://analyzingalpha.com/python-trading-tools

Quantrocket.com
Backtrader.com

trade.collective2.com seems worth taking a look for discovering possible strategies

More Tools and libraries:
hackernoon.com/9-great-tools-for-algo-trading-e0938a6856cd
https://github.com/Heerozh/spectre

Data sources:
hackernoon.com/data-data-data-11-great-financial-data-vendors-844d2cfce77d

### Subscription-based following someone else's strategy:

WealthSignals is a simple platform by the creators of Wealth Lab, an early trading automation tool which was sold to Fidelity. Two particular strategies there seem interesting:

www.wealthsignals.com/Strategy/Detail/ETF-Pairs-Arbitrage-9IP7Vx
www.wealthsignals.com/Strategy/Detail/ETFrisktrader-Y7OnzD

## Simple (short-term) Goal

Design a simple trend following strategy running on QuantConnect (QC) and try to enter it in their competition - next deadline Jan 20, 2020. Potentially emulate / learn from WealthSignals references or similar supposedly profitable automated strategies we can dig up. More sophisticated strategies will need access to a strong mathematics or statistics talent.

### Ideas

Recent update of a simple strategy from EC's 2003 book with many "recipes":
https://www.quantrocket.com/blog/leveraged-etf-intraday-momentum/


## Some of the Principles

Straight from "The Rule"

1. Get in the game (create, test and trade a strategy)
2. If you lose all your chips you can't bet (careful risk management and downside protection)
3. Know and improve the odds (statistical rigor and foundation)
4. Cut your losses and let your winnings run on. When something is not going well, stop doing it. When something is going well, continue!

- Be detached from what you are trading
- Don't be afraid to cut losses.
- Timing is our advantage. It is a positive mean game. Keep losses small but potential for big wins.
- We want money to work for us not the reverse, we would like a system that runs mostly on autopilot and not anguish with the market
- Try to device a rigorously tested Bayesian statistical approach


## References / Resources

Jim Simons book podcast (worth the listen instead of the full book):
https://open.spotify.com/episode/5GcLuIqLsMJcnfxKytQaTH?si=j8Yg7kObQziDmfsPMp3lKA

Quantitative Trading - How to Build Your Own Algorithmic Trading Business by Ernest Chan

Algorithmic Trading - Winning Strategies and Their Rational by Ernest Chan

[Inside the Black Box](https://www.amazon.com/Inside-Black-Box-Quantitative-Trading/dp/0470432063/ref=sr_1_2?crid=Q1K0P2H53QQE&keywords=inside+the+black+box&qid=1578373651&s=books&sprefix=Inside+the+black%2Cstripbooks%2C222&sr=1-2) by Rishi Narang (QuantConnect seems to be built very much on the template and knowledge described in this book)
