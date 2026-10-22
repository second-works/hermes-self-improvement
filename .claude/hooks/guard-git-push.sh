#!/usr/bin/env bash
# Claude Code PreToolUse hook for Bash.
# Blocks `git push` to main/master, force pushes, and any push from main/master.
# It reads the command text only and is not a shell parser: aliases, scripts,
# bash -c, quoted separators and other tools are not fully covered. Server-side
# branch protection is the real guarantee.
# Exit 2 blocks the tool call and shows the message to Claude.

block() {
  printf 'guard-git-push: %s\n' "$1" >&2
  exit 2
}

input="$(cat)"

# Without jq the command cannot be decoded; anything mentioning git may be a push.
if ! command -v jq >/dev/null 2>&1; then
  case "$(printf '%s' "$input" | tr -d "'\"\\")" in
    *git*) block "jq is not installed, so the push could not be checked" ;;
  esac
  exit 0
fi
if ! cmd="$(printf '%s' "$input" | jq -er '.tool_input.command' 2>/dev/null)"; then
  case "$(printf '%s' "$input" | tr -d "'\"\\")" in
    *git*) block "could not read the command from the hook input" ;;
  esac
  exit 0
fi
cwd="$(printf '%s' "$input" | jq -r '.cwd // empty' 2>/dev/null)"

# Remove "\<newline>" continuations as the shell does (not replace them with a space),
# so pu\<newline>sh stays push and ma\<newline>in stays main. A doubled backslash is
# one literal backslash, so the newline after it still ends the command: protect
# pairs first, then remove only an odd backslash before a newline.
nl=$'\n' bs='\' ph=$'\001'
cmd="${cmd//"$bs$bs"/$ph}"
cmd="${cmd//"$bs$nl"/}"
cmd="${cmd//"$ph"/$bs$bs}"

# Fast path, on the decoded command: anything that cannot be a git push is allowed.
# Quotes and backslashes are removed first, so g'it' p"ush" is not missed.
flat="$(printf '%s' "$cmd" | tr -d "'\"\\")"
case "$flat" in
  *git*) ;;
  *) exit 0 ;;
esac
case "$flat" in
  *push* | *'$'* | *'`'*) ;;
  *) exit 0 ;;
esac

# >&, <& and &> are redirections, not the & separator (git push 2>&1 origin main).
cmd="${cmd//>&/>}"
cmd="${cmd//<&/<}"
cmd="${cmd//&>/>}"

# A segment is a git command when git starts it. Allowed before git: "(", "{", "!",
# shell keywords and wrappers with their options (then, do, time, command,
# env -i, xargs, timeout 60, nice, sudo -u <user> ...),
# VAR=value prefixes, and a path such as /usr/bin/git. git's own options may come
# next; -C, -c, --git-dir, --work-tree and --namespace take a separate value.
lead='^[[:space:]({!]*((if|then|do|else|elif|while|until|time|command|exec|nohup|xargs|sudo|env|timeout|nice|ionice|stdbuf)([[:space:]]+(-[^[:space:]]+([[:space:]]+[^-[:space:]][^[:space:]]*)?|[0-9][^[:space:]]*))*[[:space:]]+|[A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+|![[:space:]]+)*([^[:space:]]*/)?git'
opts="([[:space:]]+(-C|-c|--git-dir|--work-tree|--namespace|--config-env)[[:space:]]+(\"[^\"]*\"|'[^']*'|[^[:space:]]+)|[[:space:]]+-[^[:space:]]+)*"
push_re="${lead}${opts}[[:space:]]+push([[:space:]]|\$)"
# git followed by a subcommand built from a variable or substitution.
dynamic_re="${lead}${opts}[[:space:]]+[^[:space:]-][^[:space:]]*[\$\`]"
force_re='[[:space:]](--force|--force-with-lease|--force-if-includes|--mirror|-[a-zA-Z]*f[a-zA-Z]*)([=)}<>[:space:]]|$)'
plus_re='[[:space:]:]\+[^[:space:]]'
# A redirection right after a name (main>out.log) still passes the name to git.
main_re='([[:space:]:]|refs/heads/)(main|master)([)}<>[:space:]]|$)'
# Pushes that select many branches, which can include main/master.
many_re='[[:space:]](--all|--branches)([=)}<>[:space:]]|$)|[[:space:]]:([)}<>[:space:]]|$)|\*'

found_push=0
scan() { # check every segment of the command text on stdin
  local raw plain
  while IFS= read -r raw; do
    # Push options carry free text (for example -o "ci +1" or -o "note >"); drop them
    # first, so a < or > inside the text is not taken for a redirection below. Only
    # after the first " push": before it, -o belongs to a wrapper such as xargs -o.
    head_part="${raw%%[[:space:]]push*}"
    tail_part="${raw#"$head_part"}"
    tail_part="$(printf '%s' "$tail_part" | sed -E "s/(^|[[:space:]])(-o|--push-option)(=|[[:space:]]+)(\"[^\"]*\"|'[^']*'|[^[:space:]]+)/\\1/g")"
    raw="$head_part$tail_part"
    # The shell removes redirections and their targets before git sees its arguments
    # (git>log push origin main runs "git push origin main"), so remove them here too.
    # A quoted target may contain spaces (>"/tmp/push log"), so take the whole quote.
    raw="$(printf '%s' "$raw" | sed -E "s/[0-9]*(<<<|<<|>>|<>|<|>)[[:space:]]*(\"[^\"]*\"|'[^']*'|[^[:space:]<>]+)/ /g")"
    plain="$(printf '%s' "$raw" | tr -d "'\"\\")"
    if [[ ! $raw =~ $push_re && ! $plain =~ $push_re ]]; then
      [[ $raw =~ $dynamic_re ]] && block "a git subcommand built from a variable cannot be checked; write it literally: $raw"
      continue
    fi
    found_push=1
    case "$raw" in
      *'$'* | *'`'*) block "a push built from variables or command substitution cannot be checked; write the branch name literally: $raw" ;;
    esac
    [[ $plain =~ $force_re || $plain =~ $plus_re ]] && block "force push is not allowed: $raw"
    [[ $plain =~ $main_re ]] && block "push to main/master is not allowed: $raw"
    [[ $plain =~ $many_re ]] && block "a push of several branches (--all, :, *) can include main/master: $raw"
  done
}
# Pass 1 splits on ; & | and newlines. Pass 2 also splits at $( and backticks, so a
# push inside a command substitution such as out=$(git push origin main) is found.
# Where a substitution opens, the text before it keeps a "$" mark: its value is not
# known yet, so git push origin $(echo main) still counts as built from a variable.
split_substitutions() {
  awk '{
    gsub(/\$\(/, " $\n")
    n = split($0, part, "`"); out = part[1]
    for (i = 2; i <= n; i++) out = out ((i % 2 == 0) ? " $\n" : "\n") part[i]
    print out
  }'
}
scan < <(printf '%s\n' "$cmd" | tr ';&|' '\n\n\n')
scan < <(printf '%s\n' "$cmd" | split_substitutions | tr ';&|' '\n\n\n')

if [[ $found_push -eq 1 ]]; then
  dir="${cwd:-.}"
  branch="$(git -C "$dir" symbolic-ref --short -q HEAD 2>/dev/null || true)"
  case "$branch" in
    main | master) block "push from the $branch branch is not allowed; use an Issue branch" ;;
  esac
  # Without a refspec on the command line, git takes the destination from config.
  if git -C "$dir" config --get-regexp '^remote\..*\.push$' 2>/dev/null |
    grep -Eq '([[:space:]:]|refs/heads/)(main|master)$|\*|[[:space:]]:$'; then
    block "a remote.<name>.push setting can send pushes to main/master"
  fi
  case "$(git -C "$dir" config --get push.default 2>/dev/null)" in
    matching) block "push.default=matching pushes every branch with the same name, including main/master" ;;
    upstream | tracking)
      case "$(git -C "$dir" config --get "branch.$branch.merge" 2>/dev/null)" in
        refs/heads/main | refs/heads/master) block "push.default=upstream would push $branch to its upstream main/master" ;;
      esac
      ;;
  esac
fi

exit 0
