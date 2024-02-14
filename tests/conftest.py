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
def crv():
    yield Contract("0xD533a949740bb3306d119CC777fa900bA034cd52")

@pytest.fixture
def old_proxy(strategy, gov):
    p = Contract("0xda18f789a1D9AD33E891253660Fcf1332d236b29")
    yield p


@pytest.fixture
def voter():
    yield Contract("0xF147b8125d2ef93FB6965Db97D6746952a133934")

@pytest.fixture
def strategy():
    yield Contract("0x23724D764d8b3d26852BA20d3Bc2578093d2B022")

@pytest.fixture
def crv3():
    yield Contract('0x6c3F90f043a72FA612cbac8115EE7e52BDe6E490')

@pytest.fixture
def new_proxy(strategy, gov, voter, user):
    p = user.deploy(StrategyProxy)
    # Set up new proxy
    p.setGovernance(gov)
    p.setFeeRecipient(strategy, {"from": gov})
    voter.setStrategy(p, {"from": gov})
    strategy.setProxy(p, {"from": gov})
    yield p

@pytest.fixture
def fee_distributor():
    yield Contract('0xA464e6DCda8AC41e03616F95f4BC98a13b8922Dc')

@pytest.fixture
def strategy_3crv():
    yield Contract('0xe5B3b12B6c93B725484736628A22dBcd130574D7')
    
@pytest.fixture
def whale_3crv(accounts):
    yield accounts.at("0x43b4FdFD4Ff969587185cDB6f0BD875c5Fc83f8c", force=True)

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