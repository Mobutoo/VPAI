// Force temperature=0 pour banga/coder et banga/coder_longctx (Qwen2.5-Coder, llama.cpp LXC 201).
// Tool-calling non deterministe a temperature par defaut (0.8, cote llama-server) : 4/5 fiable vs 3/3 a temp 0.
// L'agent.temperature declaratif d'opencode.json ne suffit pas : bug amont confirme sur les
// providers @ai-sdk/openai-compatible custom (temperature jamais inclus dans le body /v1/chat/completions,
// cf. github.com/anomalyco/opencode issues #25755 et #2785). Le hook chat.params mute la requete juste
// avant l'appel streamText et n'est pas soumis a ce bug.
// Detail : VPAI/.planning/handoffs/2026-07-23-opencode-banga-temperature-tool-calling.md
const FORCED_TEMPERATURE = 0
const TARGET_PROVIDER = "banga"
const TARGET_MODELS = new Set(["coder", "coder_longctx"])

export const BangaToolCallingTemperature = async () => ({
  "chat.params": async ({ model }, output) => {
    const providerID = model?.providerID ?? model?.provider?.id
    const modelID = model?.modelID ?? model?.api?.id
    if (providerID !== TARGET_PROVIDER) return
    if (!TARGET_MODELS.has(modelID)) return
    output.temperature = FORCED_TEMPERATURE
  },
})
