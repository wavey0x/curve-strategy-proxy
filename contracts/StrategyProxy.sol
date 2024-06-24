// SPDX-License-Identifier: MIT
pragma solidity ^0.8.17;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/utils/Address.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

import "../interfaces/yearn/IProxy.sol";
import "../interfaces/curve/Mintr.sol";
import "../interfaces/curve/FeeDistribution.sol";
import "../interfaces/curve/Gauge.sol";

library SafeProxy {
    function safeExecute(
        IProxy proxy,
        address to,
        uint256 value,
        bytes memory data
    ) internal {
        (bool success, ) = proxy.execute(to, value, data);
        require(success);
    }
}

interface VeCRV {
    function increase_unlock_time(uint256 _time) external;
    function locked__end(address user) external returns (uint);
}

interface IMetaRegistry {
    function get_pool_from_lp_token(address _lp) external view returns (address);
}

interface IGaugeController {
    function gauge_types(address _gauge) external view returns (int128);
}

contract StrategyProxy {
    using SafeERC20 for IERC20;
    using Address for address;
    using SafeProxy for IProxy;

    uint constant WEEK = 1 weeks;

    /// @notice Yearn's voter proxy. Typically referred to as "voter".
    IProxy public constant proxy = IProxy(0xF147b8125d2ef93FB6965Db97D6746952a133934);

    /// @notice Curve's token minter.
    address public constant mintr = 0xd061D61a4d941c39E5453435B6345Dc261C2fcE0;

    /// @notice Curve's CRV token address.
    address public constant crv = 0xD533a949740bb3306d119CC777fa900bA034cd52;

    /// @notice Curve's crvUSD address (weekly fees paid in this token).
    IERC20 public constant crvUSD = IERC20(0xf939E0A03FB07F59A73314E73794Be0E57ac1b4E);

    /// @notice Curve's fee distributor contract.
    FeeDistribution public constant feeDistribution = FeeDistribution(0xD16d5eC345Dd86Fb63C6a9C43c517210F1027914);

    /// @notice Curve's vote-escrowed Curve address.
    VeCRV public constant veCRV  = VeCRV(0x5f3b5DfEb7B28CDbD7FAba78963EE202a494e2A2);

    /// @notice Curve's meta-registry. Can pull data from the many existing curve registries.
    IMetaRegistry public constant metaRegistry = IMetaRegistry(0xF98B45FA17DE75FB1aD0e7aFD971b0ca00e379fC);

    /// @notice Curve's gauge controller.
    IGaugeController public constant gaugeController = IGaugeController(0x2F50D538606Fa9EDD2B11E2446BEb18C9D5846bB);

    /// @notice Look up the strategy approved for a given Curve gauge.
    mapping(address => address) public strategies;

    /// @notice Check if a gauge reward token is approved for claiming.
    mapping(address => bool) public rewardTokenApproved;

    /// @notice Look up the recipient approved for a given extra token (typically from bribes).
    mapping(address => address) public extraTokenRecipient;

    /// @notice Check if an address is an approved voter for gauge weights.
    mapping(address => bool) public voters;

    /// @notice Check if an address is an approved locker of CRV tokens.
    mapping(address => bool) public lockers;

    /// @notice Check if an address is an approved admin fee claimer.
    address public adminFeeRecipient;

    /// @notice Current governance address.
    address public governance;

    /// @notice Check if an address is an approved factory for deploying Curve voter strategies.
    mapping(address => bool) public approvedFactories;

    // Events so that indexers can keep track of key actions
    event GovernanceSet(address indexed governance);
    event AdminFeeRecipientSet(address indexed recipient);
    event StrategyApproved(address indexed gauge, address indexed strategy);
    event StrategyRevoked(address indexed gauge, address indexed strategy);
    event VoterApprovalSet(address indexed voter, bool indexed approved);
    event LockerApprovalSet(address indexed locker, bool indexed approved);
    event ExtraTokenRecipientApproved(address indexed token, address indexed recipient);
    event ExtraTokenRecipientRevoked(address indexed token, address indexed recipient);
    event RewardTokenApprovalSet(address indexed token, bool approved);
    event FactorySet(address indexed factory, bool indexed approved);
    event TokenClaimed(address indexed token, address indexed recipient, uint balance);

    constructor(address _adminFeeRecipient) {
        require(_adminFeeRecipient != address(0), "Empty admin fee recipient");
        governance = msg.sender;
        adminFeeRecipient = _adminFeeRecipient;
    }

    /// @notice Set curve vault factory address.
    /// @dev Must be called by governance.
    /// @param _factory Address to set as curve vault factory.
    function setFactory(address _factory, bool _allowed) external {
        require(msg.sender == governance, "!governance");
        approvedFactories[_factory] = _allowed;
        emit FactorySet(_factory, _allowed);
    }
    
    /// @notice Set governance address.
    /// @dev Must be called by current governance.
    /// @param _governance Address to set as governance.
    function setGovernance(address _governance) external {
        require(msg.sender == governance, "!governance");
        require(_governance != governance, "already set");
        governance = _governance;
        emit GovernanceSet(_governance);
    }

    /// @notice Set recipient of weekly crvUSD admin fees.
    /// @dev Only a single address can be approved at any time.
    ///  Must be called by governance.
    /// @param _recipient Address to approve for fees.
    function setAdminFeeRecipient(address _recipient) external {
        require(msg.sender == governance, "!governance");
        adminFeeRecipient = _recipient;
        emit AdminFeeRecipientSet(_recipient);
    }

    /// @notice Add strategy to a gauge.
    /// @dev Must be called by governance or factory.
    /// @param _gauge Gauge to permit strategy on.
    /// @param _strategy Strategy to approve on gauge.
    function approveStrategy(address _gauge, address _strategy) external {
        require(msg.sender == governance || approvedFactories[msg.sender], "!access");
        require(_strategy != address(0), "disallow zero");
        require(strategies[_gauge] != _strategy, "already approved");
        // @dev The following call should fail gracefully on older gauges that don't implement this interface.
        proxy.execute(_gauge, 0, abi.encodeWithSignature("set_rewards_receiver(address)", _strategy));
        strategies[_gauge] = _strategy;
        emit StrategyApproved(_gauge, _strategy);
    }

    /// @notice Clear any previously approved strategy to a gauge.
    /// @dev Must be called by governance.
    /// @param _gauge Gauge from which to remove strategy.
    function revokeStrategy(address _gauge) external {
        require(msg.sender == governance, "!governance");
        address _strategy = strategies[_gauge];
        require(_strategy != address(0), "already revoked");
        // @dev The following call should fail gracefully on older gauges that don't implement this interface.
        proxy.execute(_gauge, 0, abi.encodeWithSignature("set_rewards_receiver(address)", address(0)));
        strategies[_gauge] = address(0);
        emit StrategyRevoked(_gauge, _strategy);
    }

    /// @notice Use to approve a recipient. Typically only to be used on older gauge codebases as newer code allows
    ///         for Recipients have privileges to claim tokens directly from the voter.
    /// @dev For safety: Recipients cannot be added for LP tokens or gauge tokens (approved via gauge controller).
    ///  Must be called by governance.
    /// @param _token Token to permit a recpient for.
    /// @param _recipient Recipient to approve for token.
    function approveExtraTokenRecipient(address _token, address _recipient) external {
        require(msg.sender == governance, "!governance");
        require(_recipient != address(0), "disallow zero");
        require(extraTokenRecipient[_token] != _recipient, "already approved");
        require(_isSafeToken(_token), "!safeToken");
        extraTokenRecipient[_token] = _recipient;
        emit ExtraTokenRecipientApproved(_token, _recipient);
    }

    /// @notice Clear any previously approved token recipient.
    /// @dev Must be called by governance.
    /// @param _token Token from which to clearn recipient.
    function revokeExtraTokenRecipient(address _token) external {
        require(msg.sender == governance, "!governance");
        address recipient = extraTokenRecipient[_token];
        require(recipient != address(0), "already revoked");
        extraTokenRecipient[_token] = address(0);
        emit ExtraTokenRecipientRevoked(_token, recipient);
    }

    /// @notice Claim extra tokens sitting in the voter.
    /// @dev Must be called by an approved recipient. See approveExtraTokenRecipient()
    ///  for more info.
    /// @param _token Token to claim.
    function claimExtraToken(address _token) external {
        address recipient = extraTokenRecipient[_token];
        require(msg.sender == recipient);
        uint256 _balance = IERC20(_token).balanceOf(address(proxy));
        if (_balance > 0) {
            proxy.safeExecute(_token, 0, abi.encodeWithSignature("transfer(address,uint256)", recipient, _balance));
            emit TokenClaimed(_token, recipient, _balance);
        }
    }

    /// @notice Approve an address for voting on gauge weights.
    /// @dev Must be called by governance.
    /// @param _voter Voter to add.
    function approveVoter(address _voter, bool _approved) external {
        require(msg.sender == governance, "!governance");
        voters[_voter] = _approved;
        emit VoterApprovalSet(_voter, _approved);
    }

    /// @notice Approve an address for locking CRV.
    /// @dev Must be called by governance.
    /// @param _locker Locker to add.
    function approveLocker(address _locker, bool _approved) external {
        require(msg.sender == governance, "!governance");
        lockers[_locker] = _approved;
        emit LockerApprovalSet(_locker, _approved);
    }

    /// @notice Lock CRV into veCRV contract.
    /// @dev Must be called by governance or locker.
    function lock() external {
        require(msg.sender == governance || lockers[msg.sender], "!locker");
        uint256 amount = IERC20(crv).balanceOf(address(proxy));
        if (amount > 0) proxy.increaseAmount(amount);
    }

    /// @notice Extend veCRV lock time to maximum amount of 4 years.
    /// @dev Must be called by governance or locker.
    function maxLock() external {
        require(msg.sender == governance || lockers[msg.sender], "!locker");
        uint max = block.timestamp + (365 days * 4);
        uint lock_end = veCRV.locked__end(address(proxy));
        if(lock_end < (max / 1 weeks) * 1 weeks){
            proxy.safeExecute(
                address(veCRV), 
                0, 
                abi.encodeWithSignature("increase_unlock_time(uint256)", max)
            );
        }
    }

    /// @notice Vote on a gauge.
    /// @dev Must be called by governance or voter.
    /// @param _gauge The gauge to vote on.
    /// @param _weight Weight to vote with.
    function vote(address _gauge, uint256 _weight) external {
        require(msg.sender == governance || voters[msg.sender], "!voter");
        _vote(_gauge, _weight);
    }

    /// @notice Vote on a multiple gauges.
    /// @dev Must be called by governance or voter.
    /// @param _gauges List of gauges to vote on.
    /// @param _weights List of weight to vote with.
    function vote_many(address[] calldata _gauges, uint256[] calldata _weights) external {
        require(msg.sender == governance || voters[msg.sender], "!voter");
        require(_gauges.length == _weights.length, "!mismatch");
        for(uint256 i = 0; i < _gauges.length; i++) {
            _vote(_gauges[i], _weights[i]);
        }
    }

    function _vote(address _gauge, uint256 _weight) internal {
        proxy.safeExecute(address(gaugeController), 0, abi.encodeWithSignature("vote_for_gauge_weights(address,uint256)", _gauge, _weight));
    }

    /// @notice Withdraw exact amount of LPs from gauge.
    /// @dev Must be called by the strategy approved for the given gauge.
    /// @param _gauge The gauge from which to withdraw.
    /// @param _token The LP token to withdraw from gauge.
    /// @param _amount The exact amount of LPs with withdraw.
    function withdraw(
        address _gauge,
        address _token,
        uint256 _amount
    ) public returns (uint256) {
        require(strategies[_gauge] == msg.sender, "!strategy");
        uint256 _balance = IERC20(_token).balanceOf(address(proxy));
        proxy.safeExecute(_gauge, 0, abi.encodeWithSignature("withdraw(uint256)", _amount));
        _balance = IERC20(_token).balanceOf(address(proxy)) - _balance;
        proxy.safeExecute(_token, 0, abi.encodeWithSignature("transfer(address,uint256)", msg.sender, _balance));
        return _balance;
    }

    /// @notice Find Yearn voter's full balance within a given gauge.
    /// @param _gauge The gauge from which to check balance.
    function balanceOf(address _gauge) public view returns (uint256) {
        return IERC20(_gauge).balanceOf(address(proxy));
    }

    /// @notice Withdraw full balance of voter's LPs from gauge.
    /// @param _gauge The gauge from which to withdraw.
    /// @param _token The LP token to withdraw from gauge.
    function withdrawAll(address _gauge, address _token) external returns (uint256) {
        return withdraw(_gauge, _token, balanceOf(_gauge));
    }

    /// @notice Takes care of depositing Curve LPs into gauge.
    /// @dev Strategy must first transfer LPs to this contract prior to calling.
    ///  Must be called by strategy approved for this gauge.
    /// @param _gauge The gauge to deposit LP token into.
    /// @param _token The LP token to deposit into gauge.
    function deposit(address _gauge, address _token) external {
        require(strategies[_gauge] == msg.sender, "!strategy");
        uint256 _balance = IERC20(_token).balanceOf(address(this));
        IERC20(_token).safeTransfer(address(proxy), _balance);
        _balance = IERC20(_token).balanceOf(address(proxy));

        proxy.safeExecute(_token, 0, abi.encodeWithSignature("approve(address,uint256)", _gauge, 0));
        proxy.safeExecute(_token, 0, abi.encodeWithSignature("approve(address,uint256)", _gauge, _balance));
        proxy.safeExecute(_gauge, 0, abi.encodeWithSignature("deposit(uint256)", _balance));
    }

    /// @notice Takes care of depositing Curve LPs into gauge.
    /// @dev Strategy must first transfer LPs to this contract prior to calling.
    ///  Must be called by strategy approved for this gauge.
    /// @param _gauge The gauge to deposit LP token into.
    /// @param _token The LP token to deposit into gauge.
    function depositExact(address _gauge, address _token, uint _amount) external {
        require(strategies[_gauge] == msg.sender, "!strategy");
        IERC20(_token).safeTransfer(address(proxy), _amount);

        proxy.safeExecute(_token, 0, abi.encodeWithSignature("approve(address,uint256)", _gauge, 0));
        proxy.safeExecute(_token, 0, abi.encodeWithSignature("approve(address,uint256)", _gauge, _amount));
        proxy.safeExecute(_gauge, 0, abi.encodeWithSignature("deposit(uint256)", _amount));
    }

    /// @notice Abstracts the CRV minting and transfers to an approved strategy with CRV earnings.
    /// @dev Designed to be called within the harvest function of a strategy.
    /// @param _gauge The gauge which this strategy is claiming CRV from.
    function harvest(address _gauge) external {
        require(strategies[_gauge] == msg.sender, "!strategy");
        uint256 _balance = IERC20(crv).balanceOf(address(proxy));
        proxy.safeExecute(mintr, 0, abi.encodeWithSignature("mint(address)", _gauge));
        _balance = IERC20(crv).balanceOf(address(proxy)) - _balance;
        proxy.safeExecute(crv, 0, abi.encodeWithSignature("transfer(address,uint256)", msg.sender, _balance));
    }

    /// @notice Claim share of weekly admin fees from Curve fee distributor.
    /// @dev Admin fees become available every Thursday at 00:00 UTC
    function claimAdminFees() external returns (uint amount) {
        require(msg.sender == adminFeeRecipient, "!authorized");
        amount = _claimAdminFees();
        _transferAdminFees(adminFeeRecipient, amount);
    }

    /// @notice Allow governance to claim weekly admin fees from Curve fee distributor.
    function forceClaimAdminFees(address _recipient) external returns (uint amount) {
        require(msg.sender == governance, "!governance");
        amount = _claimAdminFees();
        _transferAdminFees(_recipient, amount);
    }

    function _claimAdminFees() internal returns (uint amount) {
        if (canClaim()) {
            address p = address(proxy);
            feeDistribution.claim_many([p, p, p, p, p, p, p, p, p, p, p, p, p, p, p, p, p, p, p, p]);
        }
        return crvUSD.balanceOf(address(proxy));
    }

    function _transferAdminFees(address _recipient, uint _amount) internal returns (uint) {
        if (_amount > 0) {
            proxy.safeExecute(address(crvUSD), 0, abi.encodeWithSignature("transfer(address,uint256)", _recipient, _amount));
        }
        return _amount;
    }

    /// @notice Cast a DAO vote
    /// @dev Allows for casting a vote in either the admin or parameter DAO.
    /// @param _target The address of the DAO contract
    /// @param _voteId Vote identifier
    /// @param _support true/false
    function dao_vote(address _target, uint _voteId, bool _support) external returns (uint amount){
        require(
            voters[msg.sender] ||
            msg.sender == governance,
            "!voter" 
        );
        require(
            _target == 0xE478de485ad2fe566d49342Cbd03E49ed7DB3356 ||
            _target == 0xBCfF8B0b9419b9A88c44546519b1e909cF330399,
            "invalid dao contract"
        );
        bytes memory data = abi.encodeWithSignature(
            "vote(uint256,bool,bool)", 
            _voteId,
            _support,
            false
        );
        proxy.safeExecute(_target, 0, data);
    }

    /// @notice Check if any admin fees are available for claim.
    function canClaim() public view returns (bool) {
        uint weekStart = block.timestamp / WEEK * WEEK;
        uint lastClaimWeek = feeDistribution.time_cursor_of(address(proxy));
        uint lastCheckpoint = feeDistribution.last_token_time();
        if (
            block.timestamp > lastClaimWeek + 1 weeks &&
            lastCheckpoint > weekStart
        ) return true;
        return false;
    }

    /// @notice Claim non-CRV token incentives from the gauge and transfer to strategy.
    /// @dev    There are two claim methods:
    ///         - new (preferred): strategy is set as the recipient in the gauge contract. Rewards are fwd'd directly to strategy.
    ///         - legacy: fallback method for old gauges that do not support `rewards_receiver` interface. In this case, reward tokens are sent to voter and then swept to strategy.
    /// @param _gauge The gauge which this strategy is claiming rewards.
    /// @param _token The token to be claimed to the approved strategy.
    function claimRewards(address _gauge, address _token) external {
        if (_claimRewards(_gauge)) return;
        address[] memory tokens = new address[](1);
        tokens[0] = _token;
        _legacyClaimRewards(_gauge, tokens);
    }

    /// @notice Claim non-CRV token incentives from the gauge and transfer to strategy.
    /// @dev Must be called by the strategy approved for the given gauge.
    /// @param _gauge The gauge which this strategy is claiming rewards.
    /// @param _tokens The token(s) to be claimed to the approved strategy.
    function claimManyRewards(address _gauge, address[] memory _tokens) external {
        if (_claimRewards(_gauge)) return;
        _legacyClaimRewards(_gauge, _tokens);
    }
    
    // use this internal function to eliminate the need for transfers when claiming extra rewards
    function _claimRewards(address _gauge) internal returns (bool) {
        require(strategies[_gauge] == msg.sender, "!strategy");
        try Gauge(_gauge).rewards_receiver(address(proxy)) returns (address receiver) {
            require(receiver == msg.sender, "strategy not reward receiver"); // Reverts txn if fails.
        }
        catch {
            return false;
        }
        Gauge(_gauge).claim_rewards(address(proxy));
        return true;
    }

    function _legacyClaimRewards(address _gauge, address[] memory _tokens) internal returns (bool) {
        for (uint256 i; i < _tokens.length; ++i) {
            require(rewardTokenApproved[_tokens[i]], "!approvedToken");
            _transferBalance(_tokens[i]);
        }
    }

    /// @notice Approve reward tokens to be claimed by strategies.
    /// @dev Must be called by governance.
    /// @param _token The token to be claimed.
    function approveRewardToken(address _token, bool _approved) external {
        require(msg.sender == governance, "!governance");
        if (_approved) require(_isSafeToken(_token),"!safeToken");
        require(rewardTokenApproved[_token] != _approved, "No approval change");
        rewardTokenApproved[_token] = _approved;
        emit RewardTokenApprovalSet(_token, _approved);
    }

    // make sure a strategy can't yoink gauge or LP tokens.
    function _isSafeToken(address _token) internal view returns (bool) {
        if (_token == crv || _token == address(crvUSD)) return false;
        try gaugeController.gauge_types(_token) {
            return false;
        }
        catch {} // @dev: Since we expect try should fail, proceed without any catch logic error here.
        address pool = metaRegistry.get_pool_from_lp_token(_token);
        if (pool != address(0)) return false;
        return true;
    }

    function _transferBalance(address _token) internal {
        proxy.safeExecute(_token, 0, abi.encodeWithSignature("transfer(address,uint256)", msg.sender, IERC20(_token).balanceOf(address(proxy))));
    }
}