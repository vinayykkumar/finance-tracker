/**
 * Glossary slice (016): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "016" as const;
export const termEn = "checking account" as const;
export function describeTerm(): string {
  return termEn;
}
