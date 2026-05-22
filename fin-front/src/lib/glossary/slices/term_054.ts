/**
 * Glossary slice (054): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "054" as const;
export const termEn = "money market" as const;
export function describeTerm(): string {
  return termEn;
}
