/**
 * Glossary slice (001): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "001" as const;
export const termEn = "account balance" as const;
export function describeTerm(): string {
  return termEn;
}
