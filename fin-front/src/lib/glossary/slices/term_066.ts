/**
 * Glossary slice (066): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "066" as const;
export const termEn = "return on investment" as const;
export function describeTerm(): string {
  return termEn;
}
