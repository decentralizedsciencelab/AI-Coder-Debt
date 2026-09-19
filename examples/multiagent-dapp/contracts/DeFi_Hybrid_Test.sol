```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

/**
 * @title DeFi_Hybrid_Test
 * @dev Implementation of a simple DeFi protocol for staking and rewards
 */
contract DeFi_Hybrid_Test is Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    // The token being staked
    IERC20 public immutable stakingToken;
    
    // The token being paid as rewards
    IERC20 public immutable rewardsToken;
    
    // Duration of rewards to be paid out (in seconds)
    uint256 public duration = 7 days;
    
    // Timestamp of when the rewards finish
    uint256 public finishAt;
    
    // Minimum of last updated time and reward finish time
    uint256 public updatedAt;
    
    // Reward to be paid out per second
    uint256 public rewardRate;
    
    // Sum of (reward rate * dt * 1e18 / total supply)
    uint256 public rewardPerTokenStored;
    
    // User address => rewardPerTokenStored
    mapping(address => uint256) public userRewardPerTokenPaid;
    
    // User address => rewards to be claimed
    mapping(address => uint256) public rewards;
    
    // Total staked
    uint256 public totalSupply;
    
    // User address => staked amount
    mapping(address => uint256) public balanceOf;

    /**
     * @dev Constructor initializes the staking and rewards tokens.
     * @param _stakingToken Address of the token to be staked.
     * @param _rewardsToken Address of the token to be used for rewards.
     */
    constructor(address _stakingToken, address _rewardsToken) {
        require(_stakingToken != address(0), "Invalid staking token address");
        require(_rewardsToken != address(0), "Invalid rewards token address");
        stakingToken = IERC20(_stakingToken);
        rewardsToken = IERC20(_rewardsToken);
    }
    
    /**
     * @dev Sets the reward duration for the staking contract.
     * @param _duration Duration in seconds for which rewards are distributed.
     */
    function setRewardsDuration(uint256 _duration) external onlyOwner {
        require(finishAt < block.timestamp, "Reward duration not finished");
        duration = _duration;
    }
    
    /**
     * @dev Adds reward to be distributed over the duration.
     * @param amount Amount of rewards to be distributed.
     */
    function notifyRewardAmount(uint256 amount) external onlyOwner {
        _updateReward(address(0));
        
        if (block.timestamp >= finishAt) {
            rewardRate = amount / duration;
        } else {
            uint256 remainingRewards = (finishAt - block.timestamp) * rewardRate;
            rewardRate = (amount + remainingRewards) / duration;
        }
        
        require(rewardRate > 0, "Reward rate = 0");
        require(
            rewardRate * duration <= rewardsToken.balanceOf(address(this)),
            "Reward amount > balance"
        );
        
        finishAt = block.timestamp + duration;
        updatedAt = block.timestamp;
    }
    
    /**
     * @dev Stake tokens to the contract.
     * @param amount Amount of tokens to stake.
     */
    function stake(uint256 amount) external nonReentrant {
        require(amount > 0, "Amount = 0");
        
        _updateReward(msg.sender);
        
        stakingToken.safeTransferFrom(msg.sender, address(this), amount);
        
        balanceOf[msg.sender] += amount;
        totalSupply += amount;
    }
    
    /**
     * @dev Withdraw staked tokens.
     * @param amount Amount of tokens to withdraw.
     */
    function withdraw(uint256 amount) external nonReentrant {
        require(amount > 0, "Amount = 0");
        require(balanceOf[msg.sender] >= amount, "Not enough staked");
        
        _updateReward(msg.sender);
        
        balanceOf[msg.sender] -= amount;
        totalSupply -= amount;
        
        stakingToken.safeTransfer(msg.sender, amount);
    }
    
    /**
     * @dev Claim rewards.
     */
    function claimReward() external nonReentrant {
        _updateReward(msg.sender);
        
        uint256 reward = rewards[msg.sender];
        if (reward > 0) {
            rewards[msg.sender] = 0;
            rewardsToken.safeTransfer(msg.sender, reward);
        }
    }
    
    /**
     * @dev Returns reward per token.
     * @return Reward per token.
     */
    function rewardPerToken() public view returns (uint256) {
        if (totalSupply == 0) {
            return rewardPerTokenStored;
        }
        
        return rewardPerTokenStored + 
            (((min(block.timestamp, finishAt) - updatedAt) * rewardRate * 1e18) / totalSupply);
    }
    
    /**
     * @dev Returns the amount of rewards a user can claim.
     * @param account Address of the user.
     * @return Amount of rewards earned.
     */
    function earned(address account) public view returns (uint256) {
        return
            ((balanceOf[account] * 
                (rewardPerToken() - userRewardPerTokenPaid[account])) / 1e18) +
            rewards[account];
    }
    
    /**
     * @dev Updates the reward for a user.
     * @param account Address of the user.
     */
    function _updateReward(address account) private {
        rewardPerTokenStored = rewardPerToken();
        updatedAt = min(block.timestamp, finishAt);
        
        if (account != address(0)) {
            rewards[account] = earned(account);
            userRewardPerTokenPaid[account] = rewardPerTokenStored;
        }
    }
    
    /**
     * @dev Returns the minimum of two values.
     * @param a First value.
     * @param b Second value.
     * @return Minimum of the two values.
     */
    function min(uint256 a, uint256 b) internal pure returns (uint256) {
        return a < b ? a : b;
    }
}
```