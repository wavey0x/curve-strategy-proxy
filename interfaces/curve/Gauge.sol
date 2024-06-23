// SPDX-License-Identifier: MIT
pragma solidity ^0.8.17;

interface Gauge {
    function deposit(uint256) external;
    function balanceOf(address) external view returns (uint256);
    function withdraw(uint256) external;
    function claim_rewards(address) external;
    function reward_tokens(uint256) external view returns (address);
    function rewards_receiver(address) external view returns (address);
}