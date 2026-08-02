/**
 * Agent skills a student can invoke explicitly from the chat picker.
 *
 * Replaces lib/experts.ts, which offered six "expert personas" that its own
 * docstring described as prompt prefixes — "no backend change, no extra token
 * cost". They changed the agent's VOICE, not what it could do. Meanwhile the
 * real capabilities (the SKILL.md files under skills/, handed to the deep agent
 * by agent/runtime.py via `skills=["/skills/"]`) had no entry point, so a fully
 * written skill like dothesis-humanize was unreachable unless a student happened
 * to phrase their request the way its description matched.
 *
 * The catalogue is FETCHED, never hardcoded here: the skills directory is the
 * single source of truth, so adding a skill makes it appear and removing one
 * makes it disappear, with no second list to forget.
 */

export type Skill = {
  /** Directory name, e.g. "dothesis-humanize". Also the directive target. */
  id: string;
  /** Display label, e.g. "Humanize". */
  name: string;
  /** The SKILL.md description — doubles as the picker's "when to use this". */
  description: string;
  /** Module ids this skill is suggested for, for the picker's grouping. */
  suggested_for: string[];
};

export const SKILLS_ENDPOINT = "/skills/list";

/**
 * Prefix the outgoing message with an explicit skill directive.
 *
 * Names the skill by id rather than describing a persona. That difference is
 * the whole point: the agent can READ /skills/<id>/SKILL.md, so this actually
 * loads the capability, where a persona line only nudged tone.
 */
export function applySkillDirective(text: string, skill: Skill | null): string {
  if (!skill) return text;
  return (
    `[Use the \`${skill.id}\` skill for this turn — read ` +
    `/skills/${skill.id}/SKILL.md and follow it.]\n\n${text}`
  );
}

/** Split into the picker's two groups: suggested for the current module, then the rest. */
export function groupSkills(
  skills: Skill[],
  focusModule?: string,
): { suggested: Skill[]; rest: Skill[] } {
  if (!focusModule) return { suggested: [], rest: skills };
  const suggested = skills.filter((s) => s.suggested_for.includes(focusModule));
  const rest = skills.filter((s) => !s.suggested_for.includes(focusModule));
  return { suggested, rest };
}
