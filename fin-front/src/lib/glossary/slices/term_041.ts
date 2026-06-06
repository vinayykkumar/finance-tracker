/**
 * Glossary slice (041): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "041" as const;
export const termEn = "index fund" as const;
export function describeTerm(): string {
  return termEn;
}
