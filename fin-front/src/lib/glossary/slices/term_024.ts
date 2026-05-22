/**
 * Glossary slice (024): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "024" as const;
export const termEn = "direct deposit" as const;
export function describeTerm(): string {
  return termEn;
}
