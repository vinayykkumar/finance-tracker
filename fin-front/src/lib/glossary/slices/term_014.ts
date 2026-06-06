/**
 * Glossary slice (014): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "014" as const;
export const termEn = "certificate of deposit" as const;
export function describeTerm(): string {
  return termEn;
}
