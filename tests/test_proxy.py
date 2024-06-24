import math, time, brownie
from brownie import Contract, web3, StrategyProxy, ZERO_ADDRESS, chain

DAY = 60 * 60 * 24
WEEK = DAY * 7
FOUR_YEARS = 365 * 60 * 60 * 24 * 4

def test_proxy_dao_vote(voter, new_proxy, gov, user):
    voter.setStrategy(new_proxy, {"from": gov})
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
    chain,
    gov,
):
    voter.setStrategy(new_proxy, {"from": gov})
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
    voter.setStrategy(new_proxy, {"from": gov})
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

    new_proxy.approveRewardToken(some_token, True, {'from': gov})
    tx = new_proxy.claimManyRewards(gauge_legacy, [some_token], {'from': strategy_legacy})