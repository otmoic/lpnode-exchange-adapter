
import asyncio
from anyio import create_task_group
import logging
from bson.son import SON
import time
import json


class Market:
    def __init__(self, exchange, bus_redis_client=None, amm_mongo_client=None):
        self.exchange = exchange
        self.bus_redis_client = bus_redis_client
        self.amm_mongo_client = amm_mongo_client
        self.market_symbol_list = []
        self.subscribe_task_group = None
        self.orderbook = {}

    def pre_symbol_list(self):
        self.load_chain_list_tokens()
        self.load_bridge_tokens()

    def load_chain_list_tokens(self) -> None:
        db = self.amm_mongo_client[self.amm_mongo_client.db_name]
        collection = db['chainList']
        documents = collection.find({}, {'tokenName': 1})
        token_list = [
            f"{document['tokenName']}/USDT" for document in documents]
        for token in token_list:
            if token not in self.market_symbol_list:
                logging.info(f"load_chain_list_tokens {token}")
                self.market_symbol_list.append(token)

    def load_bridge_tokens(self) -> None:
        db = self.amm_mongo_client[self.amm_mongo_client.db_name]
        collection = db['tokens']
        # 构建聚合管道
        pipeline = [
            SON([("$match", {"coinType": "coin"})]),
            SON([
                ("$group", {
                    "_id": "$marketName",
                    "tokenAddress": {"$addToSet": "$marketName"},
                    "tokenAddressStr": {"$first": "$address"},
                    "marketName": {"$first": "$marketName"},
                })
            ])
        ]
        cursor = collection.aggregate(pipeline)
        logging.info(f"load_bridge_tokens {cursor}")

        for doc in cursor:
            market_name_usdt = f"{doc['_id']}/USDT"
            if market_name_usdt not in self.market_symbol_list:
                logging.info(f"load_bridge_tokens {market_name_usdt}")
                self.market_symbol_list.append(market_name_usdt)

    async def get_spot_orderbook(self):
        return {
            "code": 0,
            "data": self.orderbook
        }

    async def market_subscribe_main(self):
        while True:
            self.pre_symbol_list()
            print("restart group")
            try:
                async with create_task_group() as tg:
                    self.subscribe_task_group = tg
                    tg.start_soon(self.subscribe)
                print(f'{self.exchange.id} market_subscribe_main() finished')
            except asyncio.CancelledError:
                print("market_subscribe_main() Cancelled")
                # self.exchange.close()
            except:
                print("market_subscribe_main() exception")
            finally:
                print('5 seconds sleep')
                await asyncio.sleep(5)

    async def restart_subscribe(self):
        logging.info("restart_subscribe")
        try:
            self.subscribe_task_group.cancel_scope.cancel()
        except Exception as e:
            print("组内任务异常", e)

    async def listen_message(self):
        while True:
            logging.info(f"listen_message {self.exchange.id} start")
            pubsub = self.bus_redis_client.pubsub()
            pubsub.subscribe('LP_SYSTEM_Notice')
            while True:
                try:
                    message = pubsub.get_message(
                        ignore_subscribe_messages=True)
                    if message != None:
                        logging.info(
                            f"listen_message {self.exchange.id} {message}")
                        if message['type'] == "message":
                            msg = json.loads(message['data'].decode("utf-8"))
                            print("msg", "🐟", msg)
                            if msg['type'] == "tokenCreate" or msg['type'] == "tokenDelete":
                                await self.restart_subscribe()
                    await asyncio.sleep(0.1)
                except Exception as e:
                    logging.exception("listen_message", e)
                    break

            logging.info(f"listen_message restart  10 secs")
            await asyncio.sleep(10)

    async def subscribe(self):

        i = 0
        while True:
            try:
                # print("get", symbol)
                orderbook = await self.exchange.watchOrderBookForSymbols(self.market_symbol_list, 10)
                self.updata_orderbook(orderbook)
                # print every 100th bidask to avoid wasting CPU cycles on printing
                if not i % 100:
                    # i = how many updates there were in total
                    # n = the number of the pair to count subscriptions
                    now = self.exchange.milliseconds()
                    print(self.exchange.iso8601(now), i, orderbook["symbol"],
                          orderbook['asks'][0], orderbook['bids'][0])
                i += 1
            except asyncio.CancelledError:
                print("subscribe() cancelled")
                await asyncio.sleep(5)
            except Exception as e:
                print(self.exchange.id,
                      'subscribe()', "Exception", e)
                await asyncio.sleep(5)

    def updata_orderbook(self, orderbook) -> None:
        symbol = orderbook['symbol']
        timestamp_seconds = time.time()
        timestamp_milliseconds = int(timestamp_seconds * 1000)
        self.orderbook[symbol] = {
            "stdSymbol": orderbook['symbol'],
            "symbol": symbol.replace("/", ""),
            "lastUpdateId": orderbook['nonce'],
            "timestamp": orderbook['timestamp'],
            "incomingTimestamp": timestamp_milliseconds,
            "stream": "",
            "bids": orderbook['bids'][:5],
            "asks": orderbook['asks'][:5],
        }

    async def report_status():

        pass

    async def main(self):
        async with create_task_group() as tg:
            try:
                tg.start_soon(self.market_subscribe_main)  # 主要的订阅程序
                tg.start_soon(self.listen_message)
                tg.start_soon(self.report_status)
            except asyncio.CancelledError:
                print("main() cancelled")
            except:
                print("main() exception")
