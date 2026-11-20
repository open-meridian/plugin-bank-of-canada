# Changelog

## 0.1.0

On open-meridian 0.36.0, contract 30, on core aae501d's harness. The
product owner's items 128, 129 and 140 (2026-11-19): Tier 1, one plugin for
the Bank's Valet API and its zero-coupon curve files. The dataset keys, the
records' codes and the source `boc` are proposed here, the product owner's
to approve.

- **`boc_rates`:** CORRA, a daily `fixing` with its 25th and 75th
  percentiles and total volume; the CORRA Compounded Index, an
  `index_level` based 12 June 2020 = 100; the target for the overnight
  rate, a `fixing`. Actual/365 simple, the plugin's statement.
- **`boc_curves`:** the 2, 3, 5, 7 and 10-year benchmark bond yields, each a
  `benchmark_yield` at its tenor on the benchmark curve's record (ruling
  130), semi-annual bond-equivalent. The long-term benchmark (no tenor
  stated) and the Real Return Bonds' yield are not carried.
- **`boc_curves`, too:** the zero-coupon curve, 120 `zero` points from 3 months to
  30 years, the Bank's decimals made per cent exactly, continuously
  compounded; no forwards or parameters (ruling 131).
- **`boc_fx`:** the daily exchange rates, each the `close` price of the
  currency's cash instrument in Canadian dollars, never inverted.
- **Auctions are not presented:** the Bank's `AUC_*` groups wait for the
  contract's AuctionResult kind.
- **No record minted;** no published time (the Bank states none on a value).
- **Terms in words** (`declared.BOC_TERMS`), the exchange rates' clause
  among them.
- **Pages:** the data role's Connection (with Sources) and Datasets (with
  Records).
- **Sample data:** the Bank's answers as received on 2026-11-19.

SDK 0.37.0: waits for a lost sidecar; its storage is read once registered,
on an instance run as shards or with a standby pod the shard's own folder.

SDK 0.37.1: a raw record kept from two threads at once waits instead of being dropped.
