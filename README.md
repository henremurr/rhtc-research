# RHTC Three Peaks Research Platform

A Railway-ready FastAPI service that:

- analyzes batches of article URLs with Perplexity Sonar;
- classifies results into AI/I, EFM/I, DS/I, Cross-Peak, or Other;
- maps stories to configured portfolio symbols;
- assigns bullish/bearish assessments and materiality tiers;
- optionally generates a branded PDF report.
- serves an options screening dashboard at `/options` with an RHTC research watchlist, Tradier quotes when configured, and clearly marked illustrative preview data otherwise.

## Options dashboard

Run `uvicorn main:app --reload` and open `http://127.0.0.1:8000/options/`.
The dashboard loads the shared RHTC symbol list from `/options/api/watchlist`. The list is stored in SQLite under `RHTC_DATA_DIR`; the Railway service must mount a persistent Volume at `/data` and set `RHTC_DATA_DIR=/data` to retain edits across deployments. Set `RHTC_WATCHLIST_ADMIN_TOKEN` to a private secret to authorize edits. The management UI prompts for this token when a change is saved. Do not commit the token. The first-time browser import can migrate the previous browser-local list into shared storage.

The initial research universe contains 129 symbols, including XTND and OPTX in DS/I. The watchlist is a research universe, not a verified brokerage holdings ledger. Future RHTC analysis should use the live `/options/api/watchlist` endpoint as the current symbol source.

The first screen loads 25 illustrative symbols without a Tradier token. With a sandbox token, scans are capped at 10 symbols per request to reduce the chance of exceeding Tradier's 60 market-data requests per minute; use ticker search or Peak filters to narrow the scan. Focus symbols are a curated research subset, not a verified position ledger.

Set `TRADIER_API_TOKEN` in the server environment to request Tradier market data. Set `OPENAI_API_KEY` to enable the short dashboard research note and the on-demand, cited ChatGPT analysis opened from the AI icon next to a ticker. The analysis uses current web search; without the key, the short note uses deterministic text and the symbol analysis is unavailable. `OPENAI_MODEL` optionally overrides the default model, and `OPENAI_ANALYSIS_MODEL` can override the symbol-analysis model. Keep both keys server-side; never commit tokens. No quote or trade action is submitted to a broker.

For an individual Tradier account, find the sandbox token under [Tradier API Settings](https://web.tradier.com/user/api). The dashboard defaults to `https://sandbox.tradier.com/v1`; sandbox market data is delayed about 15 minutes. Configure `TRADIER_API_TOKEN` in your server's secret variables, then test `/options/api/health` and a small `/options/api/opportunities?limit=1` request. The optional `TRADIER_BASE_URL` can be set explicitly to the sandbox URL. Do not paste the token into a browser page or commit it to this repository. Changing Railway variables may trigger a redeploy, so leave that step until deployment is approved.

Bid yield is option bid divided by the underlying share price. The scan chooses the nearest listed expiration and closest out-of-the-money call for each symbol; it does not account for existing contracts, share coverage, fees, or tax. Snapshot history is stored only in the current browser.

## Railway deployment

1. Upload all files to the root of your `rhtc-research` GitHub repository.
2. Keep `PERPLEXITY_API_KEY` in Railway Variables.
3. Railway will redeploy automatically.
4. Open `/health` to confirm the key is configured.
5. Open `/docs` to test the API.

## Test request

Use `POST /batch-analyze`:

```json
{
  "items": [
    {
      "id": "rocket-lab",
      "url": "https://www.perplexity.ai/page/example",
      "instructions": "Analyze for the RHTC DS/I framework."
    }
  ],
  "model": "sonar-pro",
  "concurrency": 1,
  "create_pdf": true,
  "report_title": "RHTC Morning Research Report"
}
```

When `create_pdf` is true, the response includes a `pdf_url`. Open that path
on your Railway domain to download the report.

## Security

Never place API keys in GitHub. Keep them only in Railway Variables.
