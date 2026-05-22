/**
 * Glossary slice (009): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "009" as const;
export const termEn = "bill pay" as const;
export function describeTerm(): string {
  return termEn;
}
