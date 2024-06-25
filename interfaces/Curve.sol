// SPDX-License-Identifier: MIT
pragma solidity ^0.8.17;

interface ICurveFi {
    function get_virtual_price() external view returns (uint256);

    function add_liquidity(
        // EURs
        uint256[2] calldata amounts,
        uint256 min_mint_amount
    ) external;

    function add_liquidity(
        // sBTC pool
        uint256[3] calldata amounts,
        uint256 min_mint_amount
    ) external;

    function add_liquidity(
        // bUSD pool
        uint256[4] calldata amounts,
        uint256 min_mint_amount
    ) external;

    function remove_liquidity_imbalance(uint256[4] calldata amounts, uint256 max_burn_amount) external;

    function remove_liquidity(uint256 _amount, uint256[4] calldata amounts) external;

    function remove_liquidity_one_coin(
        uint256 _token_amount,
        int128 i,
        uint256 min_amount
    ) external;

    function exchange(
        int128 from,
        int128 to,
        uint256 _from_amount,
        uint256 _min_to_amount
    ) external;

    function exchange_underlying(
        int128 from,
        int128 to,
        uint256 _from_amount,
        uint256 _min_to_amount
    ) external;

    function balances(int128) external view returns (uint256);

    function get_dy(
        int128 from,
        int128 to,
        uint256 _from_amount
    ) external view returns (uint256);
}

interface Zap {
    function remove_liquidity_one_coin(
        uint256,
        int128,
        uint256
    ) external;
}

interface IGauge {
    function deposit(uint256) external;
    function balanceOf(address) external view returns (uint256);
    function withdraw(uint256) external;
    function claim_rewards(address) external;
    function reward_tokens(uint256) external view returns (address);
    function rewards_receiver(address) external view returns (address);
}

interface IFeeDistribution {
    function claim(address) external returns (uint);
    function claim_many(address[20] calldata) external returns (bool);
    function last_token_time() external view returns (uint256);
    function time_cursor() external view returns (uint256);
    function time_cursor_of(address) external view returns (uint256);
}

interface IEscrow {
    function increase_unlock_time(uint256 _time) external;
    function locked__end(address user) external returns (uint);
}

interface IMetaRegistry {
    function get_pool_from_lp_token(address _lp) external view returns (address);
}

interface IGaugeController {
    function gauge_types(address _gauge) external view returns (int128);
}