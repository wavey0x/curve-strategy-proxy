import math, time, brownie
from brownie import Contract, web3, StrategyProxy, ZERO_ADDRESS, chain

DAY = 60 * 60 * 24
WEEK = DAY * 7
FOUR_YEARS = 365 * 60 * 60 * 24 * 4

def test_reward_token(
    new_proxy, user, some_token, gauge_new, gauge_legacy, dev, gov, 
    strategy_new, strategy_legacy, voter
):
    # Build some rewards
    chain.sleep(DAY)
    chain.mine()

    # Test Access Control
    with brownie.reverts('!strategy'):
        tx = new_proxy.claimRewards(gauge_new, some_token, {'from': dev})

    with brownie.reverts('!strategy'): 
        tx = new_proxy.claimManyRewards(gauge_new, [some_token], {'from': dev})

    # Ensure reward token claim goes direct to strategy
    reward_data = gauge_new.reward_data(some_token)
    tx = new_proxy.claimManyRewards(gauge_new, [some_token], {'from': strategy_new})
    assert len(tx.events['Transfer']) == 1
    transfer = tx.events['Transfer'][0]
    assert transfer.address == some_token.address
    assert transfer['value'] > 0
    assert transfer['to'] == strategy_new.address
    
    # Build some rewards
    chain.sleep(DAY)
    chain.mine()

    tx = new_proxy.revokeStrategy(strategy_new.gauge(),{'from':gov})
    with brownie.reverts('!strategy'):
        tx = new_proxy.claimManyRewards(gauge_new, [some_token], {'from': strategy_new})

    strategy_legacy
    assert False


    # new_proxy.claim({'from':strategy})

    # new_gauge = 

    # legacy_gauge = 

    # gauge.add_rewards()

    # make sure if gauge isnt added as receiver it fails.


def test_proxy_dao_vote(voter, new_proxy, gov, user):
    VOTING_CONTRACTS = {
        "dao": "0xE478de485ad2fe566d49342Cbd03E49ed7DB3356",
        "param": "0xBCfF8B0b9419b9A88c44546519b1e909cF330399",
    }
    target = Contract(VOTING_CONTRACTS['dao'])
    vote_id = target.votesLength() - 1
    amigos = '0x4444AAAACDBa5580282365e25b16309Bd770ce4a'
    new_proxy.approveVoter(amigos, True, {'from': gov})
    
    assert target.canVote(vote_id, voter)

    with brownie.reverts():
        new_proxy.dao_vote(
            VOTING_CONTRACTS['dao'],
            vote_id,
            True,
            {'from': user}
        )
    before_state = target.getVote(vote_id)
    new_proxy.dao_vote(
        VOTING_CONTRACTS['dao'],
        vote_id,
        True,
        {'from': amigos}
    )

    after_state = target.getVote(vote_id)
    assert before_state['yea'] < after_state['yea']

    chain.undo()
    new_proxy.dao_vote(
        VOTING_CONTRACTS['dao'],
        vote_id,
        True,
        {'from': gov}
    )

def test_proxy(
    accounts, 
    voter, 
    new_proxy, 
    fee_distributor,
    chain, 
    whale_crvusd, 
    gov,
    crvusd,
    user,
    dev,
):
    max = chain.time() + FOUR_YEARS
    locker = accounts[2]
    new_proxy.approveLocker(locker, True, {'from':gov})
    vecrv = Contract(new_proxy.veCRV())
    lock_end = vecrv.locked__end(voter)

    new_proxy.maxLock({'from':gov})
    if int(max/WEEK)*WEEK == lock_end:
        assert vecrv.locked__end(voter) == lock_end
        chain.sleep(60*60*24*7)
        chain.mine()
        new_proxy.maxLock({'from':gov})
    assert vecrv.locked__end(voter) > lock_end

    chain.undo(1)
    new_proxy.maxLock({'from':locker})
    assert vecrv.locked__end(voter) > lock_end

    chain.undo(1)
    new_proxy.approveLocker(locker, False, {'from':gov})
    with brownie.reverts():
        new_proxy.maxLock({'from':locker})

    # Test voting from voter approved account
    gauge = '0x8Fa728F393588E8D8dD1ca397E9a710E53fA553a'
    new_proxy.vote(gauge,0, {'from':gov})
    chain.undo(1)

    with brownie.reverts():
        chain.sleep(60*60*60)
        chain.mine()
        new_proxy.vote(gauge,0, {'from':voter})
    
    voter_user = locker
    tx = new_proxy.approveVoter(voter_user, True, {'from':gov})
    e = tx.events['VoterApprovalSet']
    assert e['voter'] == voter_user
    assert e['approved'] == True
    new_proxy.vote(gauge,0, {'from':voter_user})
    
    tx = new_proxy.approveVoter(voter_user, False, {'from':gov})
    e = tx.events['VoterApprovalSet']
    assert e['voter'] == voter_user
    assert e['approved'] == False

    with brownie.reverts():
        new_proxy.vote(gauge,0, {'from':voter_user})

def test_admin_fees(accounts, crvusd, fee_distributor, whale_crvusd, voter, new_proxy, dev, gov):
    admin = accounts.at(fee_distributor.admin(),force=True)
    crvusd.transfer(fee_distributor, 100_000e18, {'from':whale_crvusd})
    fee_distributor.checkpoint_token({'from':admin})
    chain.sleep(WEEK)
    chain.mine()
    admin_fee_recipient = accounts.at(new_proxy.adminFeeRecipient(),force=True)
    fee_distributor.checkpoint_token({'from':admin})
    
    # Claim Admin Fees
    before = crvusd.balanceOf(admin_fee_recipient) 
    crvusd.transfer(voter, 100e18, {'from':whale_crvusd})
    tx = new_proxy.claimAdminFees({'from':admin_fee_recipient})
    amt_received = tx.return_value
    after = crvusd.balanceOf(admin_fee_recipient)
    assert crvusd.balanceOf(voter) == 0
    assert amt_received > 0
    assert after - before == amt_received

    # Force Claim Admin Fees
    assert crvusd.balanceOf(dev) == 0
    tx = new_proxy.forceClaimAdminFees(dev, {'from':gov})
    assert crvusd.balanceOf(dev) == tx.return_value

def test_approve_adapter(accounts, voter, new_proxy, gov):
    # LP tokens are blocked
    # Approved gauge tokens are blocked
    # Pools are only blocked if pool address == lp token address
    TEST_CASES = {
        '0x89Ab32156e46F46D02ade3FEcbe5Fc4243B9AAeD': {
            'name': 'PNT',
            'should_succeed': True,
        },
        '0xBC19712FEB3a26080eBf6f2F7849b417FdD792CA': {
            'name': 'BOR',
            'should_succeed': True,
        },
        '0xD533a949740bb3306d119CC777fa900bA034cd52': {
            'name': 'CRV',
            'should_succeed': False,
        },
        '0xdBdb4d16EdA451D0503b854CF79D55697F90c8DF': {
            'name': 'ALCX',
            'should_succeed': True,
        },
        '0x1E212e054d74ed136256fc5a5DDdB4867c6E003F': {
            'name': '3EURpool-f Gauge',
            'should_succeed': False,
        },
        '0xd662908ADA2Ea1916B3318327A97eB18aD588b5d': {
            'name': 'a3CRV-f Gauge',
            'should_succeed': False,
        },
        '0x38039dD47636154273b287F74C432Cac83Da97e2': {
            'name': 'ag+ib-EUR-f Gauge',
            'should_succeed': False,
        },
        '0xbFcF63294aD7105dEa65aA58F8AE5BE2D9d0952A': {
            'name': '3CRV gauge',
            'should_succeed': False,
        },
        '0x6c3F90f043a72FA612cbac8115EE7e52BDe6E490': {
            'name': '3CRV token',
            'should_succeed': False,
        },
        '0xbebc44782c7db0a1a60cb6fe97d0b483032ff1c7': {
            'name': '3CRV Pool',
            'should_succeed': True,
        },
        '0x0309a528bba0394dc4a2ce59123c52e317a54604': {
            'name': 'REKT yCRV LP token',
            'should_succeed': False,
        },
        '0x9672D72D5843ca5C6b1E0CC676E106920D6a650E': {
            'name': 'REKT yCRV gauge - not approved',
            'should_succeed': True,
        },
        '0xdcef968d416a41cdac0ed8702fac8128a64241a2': {
            'name': 'FRAXBP Pool',
            'should_succeed': True, # Should succeed since this is the pool address, not LP
        },
        '0x3175df0976dfa876431c2e9ee6bc45b65d3473cc': {
            'name': 'FRAXBP token',
            'should_succeed': False,
        },
        '0xe57180685e3348589e9521aa53af0bcd497e884d': {
            'name': 'DOLA/FRAXBP token+pool',
            'should_succeed': False,
        },
    }
    WEEK = 60 * 60 * 24 * 7
    locker = accounts[2]
    new_proxy = Contract.from_abi('',new_proxy.address,new_proxy.abi,owner=gov)
    new_proxy.approveLocker(locker, True)
    vecrv = Contract(new_proxy.veCRV())
    lock_end = vecrv.locked__end(voter)
    for key in TEST_CASES:
        name = TEST_CASES[key]['name']
        should_succeed = TEST_CASES[key]['should_succeed']
        recipient = '0xFEB4acf3df3cDEA7399794D0869ef76A6EfAff52'
        print(f'Testing {name}\nExpected to revert {not should_succeed}')
        if not should_succeed:
            with brownie.reverts():
                tx = new_proxy.approveExtraTokenRecipient(key, recipient)
            with brownie.reverts():
                tx = new_proxy.approveRewardToken(key, True)
        else:
            tx = new_proxy.approveExtraTokenRecipient(key, recipient)
            tx = new_proxy.approveRewardToken(key, True)
            assert new_proxy.rewardTokenApproved(key) == True
        print(f'Gas used {tx.gas_used:_}')
        # if tx.gas_used > 1_000_000:
        #     assert False
        if new_proxy.extraTokenRecipient(key) != ZERO_ADDRESS:
            tx = new_proxy.revokeExtraTokenRecipient(key)
        if new_proxy.rewardTokenApproved(key):
            tx = new_proxy.approveRewardToken(key, False) # Revoke
