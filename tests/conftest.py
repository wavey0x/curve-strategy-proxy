import pytest, requests
from brownie import ZERO_ADDRESS, Contract, interface, StrategyProxy, web3, chain


# This causes test not to re-run fixtures on each run
@pytest.fixture(autouse=True)
def isolation(fn_isolation):
    pass


# @pytest.fixture(scope="module", autouse=True)
# def tenderly_fork(web3, chain):
#     fork_base_url = "https://simulate.yearn.network/fork"
#     payload = {"network_id": str(chain.id)}
#     resp = requests.post(fork_base_url, headers={}, json=payload)
#     fork_id = resp.json()["simulation_fork"]["id"]
#     fork_rpc_url = f"https://rpc.tenderly.co/fork/{fork_id}"
#     print(fork_rpc_url)
#     tenderly_provider = web3.HTTPProvider(fork_rpc_url, {"timeout": 600})
#     web3.provider = tenderly_provider
#     print(f"https://dashboard.tenderly.co/yearn/yearn-web/fork/{fork_id}")


@pytest.fixture
def gov(accounts):
    yield accounts.at("0xFEB4acf3df3cDEA7399794D0869ef76A6EfAff52", force=True)


@pytest.fixture
def user(accounts):
    user = accounts[0]
    yield user


@pytest.fixture
def dev(accounts):
    yield accounts[1]


@pytest.fixture
def crv():
    yield Contract("0xD533a949740bb3306d119CC777fa900bA034cd52")


@pytest.fixture
def old_proxy(gov):
    p = Contract("0xda18f789a1D9AD33E891253660Fcf1332d236b29", owner=gov)
    yield p


@pytest.fixture
def voter():
    yield Contract("0xF147b8125d2ef93FB6965Db97D6746952a133934")


@pytest.fixture
def new_proxy(gov, voter, user):
    p = user.deploy(StrategyProxy, user)
    # Set up new proxy
    p.setGovernance(gov)
    yield p


@pytest.fixture
def strategy_new(gov, new_proxy, voter):
    # assert voter.strategy() == new_proxy.address
    # Move all funds to Yearn farmer strat in order to test
    cvx_strat = Contract("0x4cf681652b9Bf9C32129b3F6edb6873e8c96eE63", owner=gov)
    yearn_strat = Contract("0x58bEf4D2361016cF2ee9ec9C0353af6FB941acD3", owner=gov)
    v = Contract(yearn_strat.vault(), owner=gov)
    s = Contract(v.withdrawalQueue(0), owner=gov)
    v.updateStrategyDebtRatio(s, 0)
    s.harvest()
    s = v.withdrawalQueue(1)
    v.updateStrategyDebtRatio(s, 0)
    s = Contract(s, owner=gov)
    s.harvest()
    # v.migrateStrategy(yearn_strat, s) # Reverting for some reason
    v.addStrategy(yearn_strat, 10_000, 0, 2**256 - 1, 0)
    voter.setStrategy(new_proxy, {"from": gov})
    v.updateStrategyDebtRatio(yearn_strat, 10_000)
    yearn_strat.setProxy(new_proxy)
    new_proxy.approveStrategy(yearn_strat.gauge(), yearn_strat, {"from": gov})
    yearn_strat.harvest()
    assert yearn_strat.estimatedTotalAssets() > 0
    yield yearn_strat


@pytest.fixture
def strategy_legacy(gov, new_proxy, voter, old_proxy):
    old = Contract("0xaBec96AC9CdC6863446657431DD32F73445E80b1", owner=gov)  # stETHv1
    new = Contract("0x95BE5AC6BEb4858B829A29E795B132D9f6799431", owner=gov)
    v = Contract(old.vault(), owner=gov)
    voter.setStrategy(old_proxy, {"from": gov})
    v.migrateStrategy(old, new)
    new.setProxy(new_proxy)
    voter.setStrategy(new_proxy, {"from": gov})
    new_proxy.approveStrategy(new.gauge(), new, {"from": gov})
    sigs = "0xa694fc3a2e1a7d4d3d18b9120000000000000000000000000000000000000000"
    yield new


@pytest.fixture
def gauge_new(accounts, user, some_token, strategy_new):
    # supports rewards_receiver
    # support rewards from admin
    # gauge_new = Contract("0xf1ce237a1E1a88F6e289CD7998A826138AEB30b0")
    gauge_new = Contract(strategy_new.gauge())
    factory = Contract(gauge_new.factory())
    admin = factory.admin()
    admin = accounts.at(admin, force=True)

    whale = accounts.at("0xC34a7c65aa08Cb36744bdA8eEEC7b8e9891e147C", force=True)
    bal = some_token.balanceOf(whale)
    some_token.transfer(user, bal, {"from": whale})
    some_token.approve(gauge_new, 2**256 - 1, {"from": user})
    distributor = user
    gauge_new.add_reward(some_token, distributor, {"from": admin})
    gauge_new.deposit_reward_token(some_token, bal / 2, {"from": distributor})
    yield gauge_new


@pytest.fixture
def gauge_legacy():
    yield Contract("0x182B723a58739a9c974cFDB385ceaDb237453c28")


@pytest.fixture
def some_token():
    yield Contract("0x57Ab1ec28D129707052df4dF418D58a2D46d5f51")  # sUSD


@pytest.fixture
def gauge_admin(gauge_new, accounts):
    factory = Contract(gauge_new.factory())
    admin = factory.admin()
    admin = accounts.at(admin, force=True)
    yield admin


@pytest.fixture
def crvusd(new_proxy):
    yield Contract(new_proxy.crvUSD())


@pytest.fixture
def fee_distributor(new_proxy):
    yield Contract(new_proxy.feeDistribution())


@pytest.fixture
def strategy_3crv():
    yield Contract("0xe5B3b12B6c93B725484736628A22dBcd130574D7")


@pytest.fixture
def whale_crvusd(accounts):
    yield accounts.at("0x4e59541306910aD6dC1daC0AC9dFB29bD9F15c67", force=True)


@pytest.fixture
def weth_amount(accounts, weth, gov):
    amount = 1e21
    # In order to get some funds for the token you are about to use,
    # it impersonate an exchange address to use it's funds.
    reserve = accounts.at("0x2F0b23f53734252Bda2277357e97e1517d6B042A", force=True)
    weth.transfer(gov, amount, {"from": reserve})
    yield amount


@pytest.fixture(scope="session")
def RELATIVE_APPROX():
    yield 1e-5
