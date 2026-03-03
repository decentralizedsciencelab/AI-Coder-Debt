// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "./Token.sol";

contract Exchange {
    Token public token;
    address public owner;
    uint256 public rate;

    event Swap(address indexed user, uint256 ethAmount, uint256 tokenAmount);

    constructor(address _tokenAddress, uint256 _rate) {
        token = Token(_tokenAddress);
        owner = msg.sender;
        rate = _rate;
    }

    function swap() public payable {
        uint256 tokenAmount = msg.value * rate;
        require(token.balanceOf(address(this)) >= tokenAmount, "Insufficient liquidity");
        token.transfer(msg.sender, tokenAmount);
        emit Swap(msg.sender, msg.value, tokenAmount);
    }

    function setRate(uint256 _rate) public {
        require(msg.sender == owner, "Only owner");
        rate = _rate;
    }
}
