// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract InterestModel {
    uint256 public baseRatePerYear;

    constructor(uint256 _baseRatePerYear) {
        baseRatePerYear = _baseRatePerYear;
    }

    function calculateInterestRate(uint256 _borrowAmount, uint256 _totalBorrows) external view returns (uint256) {
        return baseRatePerYear + (_borrowAmount * 100 / _totalBorrows);
    }
}