# RHTC Three Peaks Research Platform

A Railway-ready FastAPI service that:

- analyzes batches of article URLs with Perplexity Sonar;
- classifies results into AI/I, EFM/I, DS/I, Cross-Peak, or Other;
- maps stories to configured portfolio symbols;
- assigns bullish/bearish assessments and materiality tiers;
- optionally generates a branded PDF report.

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
