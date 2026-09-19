// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./InterestModel.sol";
import "./PriceOracle.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract LendingPool {
    ERC20 public collateralToken;
    PriceOracle public priceOracle;
    InterestModel public interestModel;

    constructor(ERC20 _collateralToken, PriceOracle _priceOracle, InterestModel _interestModel) {
        collateralToken = _collateralToken;
        priceOracle = _priceOracle;
        interestModel = _interestModel;
    }

    function deposit(uint256 amount) external {
        require(collateralToken.transferFrom(msg.sender, address(this), amount), "Transfer failed");
    }

    function withdraw(uint256 amount) external {
        require(collateralToken.transfer(msg.sender, amount), "Transfer failed");
    }
}