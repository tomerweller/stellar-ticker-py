from time import time
import json
import toml
import requests
import argparse
from urllib import urlencode

PAGE_LIMIT = 200


def millis():
    """current time in millis since epoch"""
    return int(round(time() * 1000))


def get_asset_params(prefix, atype, code, issuer):
    """get aggregation request parameters for single asset"""
    return {
        prefix + "_asset_type": atype,
        prefix + "_asset_code": code,
        prefix + "_asset_issuer": issuer,
    }


def get_asset_param_from_pair(pair, prefix):
    """get aggregation request parameters for asset pair"""
    if pair[prefix + "_asset_issuer"] == "native":
        return get_asset_params(prefix, "native", "", "")
    else:
        return get_asset_params(prefix, "credit_alphanum4", pair[prefix + "_asset_code"],
                                pair[prefix + "_asset_issuer"])


def get_aggregation_params(pair, start, end, resolution):
    """generate aggregation request params for asset pair"""
    params = {
        "order": "asc",
        "limit": PAGE_LIMIT,
        "start_time": start,
        "end_time": end,
        "resolution": resolution
    }
    params.update(get_asset_param_from_pair(pair, "base"))
    params.update(get_asset_param_from_pair(pair, "counter"))
    return params


def sum_tuples(t1, t2):
    """sum all items in two tuples to a third one. tuples must match in size"""
    return tuple(sum(t) for t in zip(t1, t2))


def aggregate_pair(horizon_host, pair, start, end, resolution):
    """fetch all trades from given time period and aggregate"""
    print "aggregating pair: ", pair["name"]
    values = (0, 0, 0)
    params = get_aggregation_params(pair, start, end, resolution)
    url = horizon_host + "/trade_aggregations?" + urlencode(params)
    consumed = False
    while not consumed:
        json_result = requests.get(url).json()
        records = json_result['_embedded']['records']
        for record in records:
            values = sum_tuples(values, (record["base_volume"], record["counter_volume"], record["trade_count"]))
        consumed = len(records) < PAGE_LIMIT
        url = json_result["_links"]["next"]
    return values


def aggregate_pairs(horizon_host, pairs, start, end, resolution):
    """"""
    retval = {}
    for pair in pairs:
        name = pair["name"]
        if name not in retval:
            retval[name] = (0, 0, 0)
        retval[name] = sum_tuples(retval[name], aggregate_pair(horizon_host, pair, start, end, resolution))
    return retval


def format_pair_result(pair_name, pair_tuple):
    """"""
    return {
        "name": pair_name,
        "base_volume": pair_tuple[0],
        "counter_volume": pair_tuple[1],
        "trade_count": pair_tuple[2],
        "price": pair_tuple[1] / pair_tuple[0] if pair_tuple[0] != 0 else 0
    }


def main():
    """"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs_toml", default="pairs.toml", help="path to toml file containing asset pairs")
    parser.add_argument("--horizon_host", default="http://localhost:8000",
                        help="horizon host (including scheme and port)")  # default to public horizon livenet
    parser.add_argument("--time_duration", type=int, default=86400000,
                        help="time duration in millis")  # default to one day
    parser.add_argument("--bucket_resolution", type=int, default=300000,
                        help="bucket resolution for aggregation")  # default to 5min
    parser.add_argument("--output_file", default="ticker.json", help="output file path")
    args = parser.parse_args()

    config = toml.load(args.pairs_toml)
    now = millis()
    end_time = now - (now % args.bucket_resolution)
    state = aggregate_pairs(args.horizon_host, config["pair"], end_time - args.time_duration, end_time,
                            args.bucket_resolution)
    formatted_pairs = [format_pair_result(pair_name, pair_tuple) for pair_name, pair_tuple in state.iteritems()]

    # dump pretty json to file
    with open(args.output_file, 'w') as outfile:
        json.dump({
            "pairs": formatted_pairs,
            "last_updated": end_time
        }, outfile, indent=4, sort_keys=True)


if __name__ == "__main__":
    main()
