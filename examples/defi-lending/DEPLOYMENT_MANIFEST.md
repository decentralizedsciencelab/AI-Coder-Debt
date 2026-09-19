# Deployment Manifest

## Deployment Order
| Step | Contract       | Dependencies             | Constructor Args                     |
|------|----------------|--------------------------|--------------------------------------|
| 1    | CollateralToken| None                     | None                                 |
| 2    | PriceOracle    | None                     | None                                 |
| 3    | InterestModel  | None                     | baseRatePerYear                      |
| 4    | LendingPool    | CollateralToken, PriceOracle, InterestModel | collateralToken, priceOracle, interestModel |

## Post-Deployment Setup
1. Set prices in PriceOracle.
2. Users must approve LendingPool to spend their CollateralToken.

## Dependency Graph
CollateralToken --> LendingPool
PriceOracle --> LendingPool
InterestModel --> LendingPool