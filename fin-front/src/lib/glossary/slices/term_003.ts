/**
 * Glossary slice (003): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "003" as const;
export const termEn = "asset allocation" as const;
export function describeTerm(): string {
  return termEn;
}
