/**
 * Glossary slice (002): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "002" as const;
export const termEn = "annual percentage rate" as const;
export function describeTerm(): string {
  return termEn;
}
