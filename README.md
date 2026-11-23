# bswan0002/skills

Reusable instructions for your coding agent. Add skills with the [skills CLI](https://github.com/vercel-labs/skills).

## Add skills

Run this command in your project, then select the skills and agents:

```bash
npx skills add bswan0002/skills
```

To add one skill:

```bash
npx skills add bswan0002/skills --skill pr-review
```

Installation is project-local by default. To use skills across projects, install globally:

```bash
npx skills add bswan0002/skills --global
```

## Update skills

Update your installed skills, including skills from other repositories:

```bash
npx skills update
```

## Available skills

Choose a skill for your task:

- [create-or-update-pr](skills/create-or-update-pr/SKILL.md): Propose and publish GitHub PRs with approval, alongside available PR guidance
- [grill-me](skills/grill-me/SKILL.md): Stress-test a plan or decision through questions. Adapted from [Matt Pocock](skills/grill-me/ATTRIBUTION.md)
- [pr-review](skills/pr-review/SKILL.md): Review a published GitHub pull request without changing it
- [qq](skills/qq/SKILL.md): Answer questions without making changes
- [technical-writing](skills/technical-writing/SKILL.md): Write and review docs, READMEs, RFCs, PR descriptions, and commit messages to a layered standard. Adapted from [poteto](skills/technical-writing/ATTRIBUTION.md)
- [unslop](skills/unslop/SKILL.md): Cut AI tells from any writing. Copied from [poteto](skills/unslop/ATTRIBUTION.md)
- [writing-for-agents](skills/writing-for-agents/SKILL.md): Write skills and other documents for agents. Copied from [Matt Pocock](skills/writing-for-agents/ATTRIBUTION.md)

## License

[MIT](LICENSE).
