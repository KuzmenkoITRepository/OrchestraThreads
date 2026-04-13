# TODO-FIX-WPS

This note records the `wemake-python-styleguide` (`WPS`) rules that are currently ignored globally in `setup.cfg` or suppressed locally with `# noqa` in this repository.

| Code | Rule name | What it checks | Practical meaning |
| --- | --- | --- | --- |
| `WPS110` | `WrongVariableNameViolation` | Forbids blacklisted variable names. | Flags vague names like `item`, `data`, `result`, `arr`, or `tmp` when a more specific name would be clearer. |
| `WPS111` | `TooShortNameViolation` | Forbids short variable or module names. | Pushes names away from one-letter or cryptic abbreviations unless they are in narrow accepted cases. |
| `WPS202` | `TooManyModuleMembersViolation` | Limits the number of top-level functions and classes in a module. | Signals that a file has grown too large and should likely be split by responsibility. |
| `WPS210` | `TooManyLocalsViolation` | Limits the number of local variables in a function. | Usually means a function is doing too much and should be decomposed. |
| `WPS211` | `TooManyArgumentsViolation` | Limits the number of function or method arguments. | Suggests grouping related inputs into a typed object or simplifying the API. |
| `WPS212` | `TooManyReturnsViolation` | Limits the number of `return` statements in a function. | Too many exit points often make branching logic harder to follow. |
| `WPS214` | `TooManyMethodsViolation` | Limits the number of methods in a class. | Warns that a class may have become too broad or god-object-like. |
| `WPS215` | `TooManyBaseClassesViolation` | Limits the number of base classes. | Discourages wide multiple inheritance hierarchies that are hard to reason about. |
| `WPS217` | `TooManyAwaitsViolation` | Limits the number of `await` expressions in one function. | Highlights async functions that are getting too procedural and overloaded. |
| `WPS218` | `TooManyAssertsViolation` | Limits the number of `assert` statements in one function. | Often appears in tests that check too many things at once. |
| `WPS226` | `OverusedStringViolation` | Forbids repeated string literals. | Encourages extracting repeated strings into named constants. |
| `WPS230` | `TooManyPublicAttributesViolation` | Limits the number of public attributes on a class. | Signals that a model or state object may be too large. |
| `WPS237` | `TooComplexFormattedStringViolation` | Forbids overly complex f-strings. | Formatting expressions inside `{...}` should stay simple and readable. |
| `WPS305` | `FormattedStringViolation` | Legacy rule that used to forbid f-strings. | Historical ignore only; this rule is disabled in modern WPS releases and effectively superseded by current tooling expectations. |
| `WPS306` | `ExplicitObjectBaseClassViolation` | Legacy rule that used to forbid explicit `object` inheritance. | Historical ignore only; Python 3 no longer needs `class X(object)`, and the rule is disabled in modern WPS releases. |
| `WPS326` | `ImplicitStringConcatenationViolation` | Forbids implicit string literal concatenation. | Disallows adjacent literals like `"a" "b"` because they are easy to miss. |
| `WPS338` | `WrongMethodOrderViolation` | Enforces a consistent method order inside classes. | Keeps classes predictable by ordering special, public, protected, and private methods consistently. |
| `WPS342` | `ImplicitRawStringViolation` | Requires raw strings where escape-heavy strings are used. | Commonly pushes regex-style strings toward `r"..."` form. |
| `WPS421` | `WrongFunctionCallViolation` | Forbids certain discouraged builtin function calls. | Common examples include `print` or `input` in production-oriented code paths. |
| `WPS430` | `NestedFunctionViolation` | Forbids nested function definitions. | Encourages moving inner `def` blocks out to top level or another helper. |
| `WPS432` | `MagicNumberViolation` | Forbids unexplained numeric literals. | Pushes hard-coded numbers into named constants when they carry domain meaning. |
| `WPS433` | `NestedImportViolation` | Forbids imports inside functions or methods. | Prefers imports at module top level unless there is a strong reason not to. |
| `WPS440` | `BlockAndLocalOverlapViolation` | Forbids reusing a name across block-local and surrounding local scopes. | Avoids confusing shadowing between loop, context-manager, or exception variables and nearby locals. |
| `WPS476` | `AwaitInLoopViolation` | Forbids `await` directly inside loops. | Sequential `await` in `for` or `while` often indicates avoidable latency or batching opportunities. |
| `WPS501` | `UselessFinallyViolation` | Forbids `try/finally` without `except`. | Often means the code should use a context manager instead of manual cleanup. |
| `WPS602` | `StaticMethodViolation` | Forbids `@staticmethod`. | The styleguide prefers module functions or `@classmethod` over static methods. |
| `WPS615` | `UnpythonicGetterSetterViolation` | Forbids Java-style getters and setters. | Prefers `@property` or direct attribute access over `get_x()` and `set_x()` patterns. |

## Notes

- `WPS305` and `WPS306` remain listed in the repo config as historical global ignores, but both are considered legacy in modern `wemake-python-styleguide` releases.
- This file is documentation only. It does not claim that every ignore is wrong; it exists to make future cleanup work explicit and easier to prioritize.
