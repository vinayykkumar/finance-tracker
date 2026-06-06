/**
 * Glossary slice (072): modular copy for future i18n / tooltips.
 * @see README in parent folder.
 */
export const termId = "072" as const;
export const termEn = "tax withholding" as const;
export function describeTerm(): string {
  return termEn;
}
