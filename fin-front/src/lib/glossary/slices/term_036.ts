/**
 * Glossary slice (036): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "036" as const;
export const termEn = "gross income" as const;
export function describeTerm(): string {
  return termEn;
}
