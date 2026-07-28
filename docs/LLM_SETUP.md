# LLM Setup

The LLM edits job specifications. It does not directly control Blender during standard builds.

Job changes remain proposals until they pass canonical Job v2 validation and the
operator approves the displayed field-level diff. The LLM may suggest registry
`asset_ids`, palettes, semantic overrides, animation packs, export profiles, and
structured corrective diagnostics. It cannot propose source paths, credentials,
code, or commands. Animation creation, QA, Blender export, and the Godot import
gate are entirely deterministic and do not invoke an LLM.

## Ollama

1. Install Ollama.
2. Pull a JSON-capable coding/instruction model.
3. Set `llm_provider` to `ollama` in `config/settings.json`.
4. Set `ollama_model` to the installed model name.

Recommended starting point:

```text
qwen2.5-coder:7b
```

A larger model may follow instructions more reliably, but the build system itself remains deterministic.

## OpenAI-compatible endpoint

1. Set `llm_provider` to `openai`.
2. Set `openai_base_url`.
3. Set `openai_model`.
4. Set the `OPENAI_API_KEY` environment variable.

## Security

Never store API keys in character JSON files or project source. Use environment variables.
The preflight dashboard warns when the selected provider is unavailable. LLM
responses are untrusted input: unsupported fields and non-assembly source changes
are rejected before canonical job validation, preview, or apply.
