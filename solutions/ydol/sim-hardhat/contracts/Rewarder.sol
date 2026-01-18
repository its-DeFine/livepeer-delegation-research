// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

interface IMintable {
    function mint(address to, uint256 value) external;
}

contract Rewarder {
    address public owner;
    address public immutable rewardToken;
    uint256 public rewardPerUnit; // reward tokens minted per 1e18 of input amount

    event OwnerUpdated(address indexed owner);
    event RewardPerUnitUpdated(uint256 rewardPerUnit);

    modifier onlyOwner() {
        require(msg.sender == owner, "NOT_OWNER");
        _;
    }

    constructor(address rewardToken_, address owner_) {
        require(rewardToken_ != address(0) && owner_ != address(0), "BAD_ADDR");
        rewardToken = rewardToken_;
        owner = owner_;
        emit OwnerUpdated(owner_);
    }

    function setRewardPerUnit(uint256 rewardPerUnit_) external onlyOwner {
        rewardPerUnit = rewardPerUnit_;
        emit RewardPerUnitUpdated(rewardPerUnit_);
    }

    function onSwap(address swapper, uint256 amountIn) external {
        // toy model: reward proportional to input amount, denominated in 1e18.
        if (rewardPerUnit == 0) return;
        uint256 reward = (amountIn * rewardPerUnit) / 1e18;
        if (reward == 0) return;
        IMintable(rewardToken).mint(swapper, reward);
    }
}

