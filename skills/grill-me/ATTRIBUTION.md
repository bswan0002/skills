# Attribution

Original skill instructions by Matt Pocock, from [mattpocock/skills](https://github.com/mattpocock/skills), licensed under the MIT License (see [LICENSE](LICENSE)).

Upstream snapshot: [24fe0ef7737efae15c87225755e9f6f5965e4888](https://github.com/mattpocock/skills/commit/24fe0ef7737efae15c87225755e9f6f5965e4888).

Sources:
- [grill-me/SKILL.md](https://raw.githubusercontent.com/mattpocock/skills/24fe0ef7737efae15c87225755e9f6f5965e4888/skills/productivity/grill-me/SKILL.md): skill name.
- [grilling/SKILL.md](https://raw.githubusercontent.com/mattpocock/skills/24fe0ef7737efae15c87225755e9f6f5965e4888/skills/productivity/grilling/SKILL.md): description and instruction body, preserved verbatim, with model invocation enabled as upstream.
- [grilling/agents/openai.yaml](https://raw.githubusercontent.com/mattpocock/skills/24fe0ef7737efae15c87225755e9f6f5965e4888/skills/productivity/grilling/agents/openai.yaml): agent metadata, with only the display name changed to "Grill Me" to match the consolidated skill. Uses the upstream `grilling` invocation policy rather than the wrapper's restriction on implicit invocation.

Consolidation uses `grilling` under the `grill-me` name, replacing the wrapper's Skill-tool call with the complete instruction body. No upstream prose has been edited; no separate `grilling` installation is required. The skill can be invoked by the model from natural-language requests, not only by slash command.
