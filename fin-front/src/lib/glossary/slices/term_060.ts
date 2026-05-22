/**
 * Glossary slice (060): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "060" as const;
export const termEn = "payroll" as const;
export function describeTerm(): string {
  return termEn;
}
