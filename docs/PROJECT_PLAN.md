# Project Plan

## Current Direction

The project is now the Missouri Public Data AI Assistant: a source-grounded assistant that retrieves Missouri public-record evidence through local tools and, when configured, uses Vertex AI Gemini to synthesize a clearer answer from that evidence.

The historical local-model work remains useful evidence of iteration discipline, but it is no longer the main product direction.

## Success Criteria

A reviewer should be able to understand four things quickly:

- what Missouri public-data sources are indexed
- how the assistant retrieves evidence and cites sources
- how Deep Answer Mode uses Vertex AI without relying on model memory
- how privacy, unsupported-scope, and missing-provider cases fail safely

## Runtime Architecture

```text
user question
  -> local guardrails
  -> source-family routing
  -> local evidence tool
  -> compact evidence bundle
  -> Vertex AI Gemini synthesis when available
  -> local verification metadata
  -> final answer with citations, confidence, and limitations
```

The local evidence tools are:

- `search_public_records`
- `exact_record_lookup`
- `source_family_search`
- `compare_records`
- `aggregate_public_records`

## What Stays In Scope

- Missouri public-record lookup and source discovery
- cited aggregate values, rankings, comparisons, and report explanations
- local deterministic lookup for exact public records
- fake and unavailable providers for tests without cloud credentials
- historical LoRA reports as background evidence

## What Stays Out Of Scope

- official State of Missouri representation
- legal, procurement, financial, employment, medical, or policy advice
- private identifiers or contact enrichment
- model-memory answers for exact public records
- new datasets until retrieval, ranking, and demo quality are stable

## Next Build Priorities

1. Keep the data surface frozen.
2. Improve shared evidence ranking across existing indexes.
3. Add more multi-tool complex-question tests.
4. Run a live Vertex smoke test after credentials are configured.
5. Keep the public repo focused on the assistant, not the old local-model experiment.
