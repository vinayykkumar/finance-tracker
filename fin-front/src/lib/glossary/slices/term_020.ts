/**
 * Glossary slice (020): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "020" as const;
export const termEn = "credit score" as const;
export function describeTerm(): string {
  return termEn;
}
