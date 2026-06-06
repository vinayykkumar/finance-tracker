/**
 * Glossary slice (015): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "015" as const;
export const termEn = "chargeback" as const;
export function describeTerm(): string {
  return termEn;
}
