#!/usr/bin/env bash
#
# get_cenarios.sh - baixa o conteúdo dos cenários listados em sources.txt
#
# Para cada linha do arquivo do tipo
#   https://github.com/spgroup/mergedataset/tree/master/<projeto>/<commit>
# o script cria a pasta <projeto>/ (caso não exista) e baixa dentro dela o
# conteúdo da URL, gravando em <projeto>/<commit>/. Ao terminar volta para a
# pasta raiz e repete o processo para a próxima linha.
#
# O download usa um clone parcial (--filter=blob:none) do repositório apontado
# nas URLs: só o esqueleto de diretórios é baixado no início e, a cada linha,
# apenas os arquivos daquele commit são trazidos. Assim não é necessário clonar
# o repositório inteiro nem depender da API do GitHub (limite de requisições).
#
# Binários .jar NÃO são baixados por padrão (--exclude-jars é o padrão). Para
# baixar tudo, inclusive os .jar, use --full: nesse caso o script pede
# confirmação antes de continuar (resposta padrão: não).
#
# Uso:
#   ./get_cenarios.sh                     # usa ./sources.txt e grava na pasta do script
#   ./get_cenarios.sh -f lista.txt        # outro arquivo de entrada
#   ./get_cenarios.sh -o dados            # grava em outra pasta raiz
#   ./get_cenarios.sh --exclude-jars      # padrão: ignora arquivos .jar
#   ./get_cenarios.sh --full              # baixa também os .jar (pede confirmação)
#   ./get_cenarios.sh --full --yes        # idem, sem pedir confirmação
#   ./get_cenarios.sh --force             # rebaixa cenários que já existem
#   ./get_cenarios.sh --dry-run           # só mostra o que seria feito
#
# Uma linha já baixada (pasta <projeto>/<commit> com conteúdo) é ignorada, de
# modo que rodar o script de novo continua de onde parou.
#
set -uo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
SOURCES="$ROOT/sources.txt"
FORCE=0
DRY_RUN=0
FULL=0          # 0 = --exclude-jars (padrão, sem .jar) | 1 = --full (com .jar)
ASSUME_YES=0    # 1 = --yes (não pergunta na confirmação do --full)

usage() {
  awk 'NR > 1 { if ($0 !~ /^#/) exit; sub(/^# ?/, ""); print }' "${BASH_SOURCE[0]}"
}

log()  { printf '%s\n' "$*"; }
err()  { printf 'erro: %s\n' "$*" >&2; }
die()  { err "$*"; exit 1; }

# Confirmação do --full. Qualquer coisa diferente de s/S/y/Y/sim conta como não.
confirm_full() {
  local answer=
  printf '%s' "O uso da flag --full baixará binários .jar podendo ocupar muito espaço em sua máquina. Deseja continuar? (s/N) "
  IFS= read -r answer || answer=
  case $answer in
    s|S|y|Y|sim|Sim|SIM) return 0 ;;
    *) return 1 ;;
  esac
}

while (($#)); do
  case $1 in
    -f|--file)  [[ $# -ge 2 ]] || die "$1 exige um argumento"; SOURCES=$2; shift 2 ;;
    -o|--out)   [[ $# -ge 2 ]] || die "$1 exige um argumento"; ROOT=$2; shift 2 ;;
    -F|--force) FORCE=1; shift ;;
    -n|--dry-run) DRY_RUN=1; shift ;;
    --exclude-jars|--no-jars) FULL=0; shift ;;
    --full|--include-jars)    FULL=1; shift ;;
    -y|--yes)   ASSUME_YES=1; shift ;;
    -h|--help)  usage; exit 0 ;;
    *)          err "argumento desconhecido: $1"; usage >&2; exit 2 ;;
  esac
done

command -v git >/dev/null 2>&1 || die "git não encontrado no PATH"
[[ -r $SOURCES ]] || die "não consigo ler o arquivo de entrada: $SOURCES"

# raiz absoluta (o loop sempre volta para ela)
mkdir -p -- "$ROOT" || die "não consigo criar a pasta raiz: $ROOT"
ROOT=$(cd -- "$ROOT" && pwd) || die "não consigo acessar a pasta raiz: $ROOT"
SOURCES=$(cd -- "$(dirname -- "$SOURCES")" && pwd)/$(basename -- "$SOURCES")

# ---------------------------------------------------------------------------
# Lê o arquivo de entrada: valida cada linha e monta a lista de cenários.
# ---------------------------------------------------------------------------
url_re='^https?://github\.com/([^/]+)/([^/]+)/tree/([^/]+)/([^/]+)/([0-9a-fA-F]{40})(/.*)?$'

owners=() repos=() refs=() projects=() commits=() urls=()
declare -A seen=()
lineno=0
invalid=0

while IFS= read -r raw || [[ -n $raw ]]; do
  lineno=$((lineno + 1))
  line=${raw%$'\r'}                        # remove CR de arquivos CRLF
  line=${line#"${line%%[![:space:]]*}"}     # espaços à esquerda
  line=${line%"${line##*[![:space:]]}"}     # espaços à direita
  [[ -z $line || $line == \#* ]] && continue

  if [[ ! $line =~ $url_re ]]; then
    err "linha $lineno ignorada (formato não reconhecido): $line"
    invalid=$((invalid + 1))
    continue
  fi
  owner=${BASH_REMATCH[1]}; repo=${BASH_REMATCH[2]}; ref=${BASH_REMATCH[3]}
  project=${BASH_REMATCH[4]}; commit=${BASH_REMATCH[5]}

  key="$owner/$repo/$ref/$project/$commit"
  [[ -n ${seen[$key]:-} ]] && continue     # evita baixar a mesma URL duas vezes
  seen[$key]=1

  owners+=("$owner"); repos+=("$repo"); refs+=("$ref")
  projects+=("$project"); commits+=("$commit")
  urls+=("$line")
done < "$SOURCES"

total=${#urls[@]}
((invalid > 0)) && err "$invalid linha(s) inválida(s) em $SOURCES"
((total > 0)) || die "nenhuma URL válida encontrada em $SOURCES"

log "entrada : $SOURCES"
log "raiz    : $ROOT"
log "cenários: $total (linhas únicas)"
[[ $DRY_RUN -eq 1 ]] && log "modo    : --dry-run (nada será baixado)"
if ((FULL)); then
  log "binários: incluídos (.jar)"
else
  log "binários: ignorados (.jar — use --full para incluir)"
fi
log

# ---------------------------------------------------------------------------
# --full pede confirmação antes de baixar qualquer coisa (padrão: não)
# ---------------------------------------------------------------------------
if ((FULL)) && ((DRY_RUN == 0)) && ((ASSUME_YES == 0)); then
  if ! confirm_full; then
    err "cancelado: nada foi baixado (use --full --yes para baixar sem confirmação)"
    exit 1
  fi
  log "confirmado: os arquivos .jar também serão baixados"
  log
fi

# ---------------------------------------------------------------------------
# Clone parcial: um por repositório (owner/repo/ref) citado no arquivo.
# ---------------------------------------------------------------------------
WORK=$(mktemp -d "${TMPDIR:-/tmp}/get_cenarios.XXXXXX") || die "mktemp falhou"
cleanup() { rm -rf -- "$WORK"; }
trap cleanup EXIT INT TERM

declare -A remotes_ready=()

# prepare_remote <owner> <repo> <ref>
prepare_remote() {
  local owner=$1 repo=$2 ref=$3
  local dir="$WORK/${owner}__${repo}__${ref}"
  remotes_ready[$owner/$repo/$ref]=$dir
  [[ $DRY_RUN -eq 1 ]] && return 0
  log "preparando clone parcial de $owner/$repo (ref: $ref) ..."
  (
    set -e
    mkdir -p "$dir" && cd "$dir"
    git init -q .
    git remote add origin "https://github.com/$owner/$repo.git"
    git config core.sparseCheckout true
    git sparse-checkout init --no-cone
    git fetch -q --depth=1 --filter=blob:none origin "$ref"
    git update-ref "refs/heads/$ref" FETCH_HEAD
    git symbolic-ref HEAD "refs/heads/$ref"
  ) || return 1
  return 0
}

# ---------------------------------------------------------------------------
# Baixa o conteúdo de um cenário para <ROOT>/<projeto>/<commit>.
# Retorna 0 = baixado, 3 = já existia (ignorado), 1 = falha.
# Deixa em LAST_FILES/LAST_JARS a contagem de arquivos copiados e de .jar do
# cenário (que só são baixados com --full).
# ---------------------------------------------------------------------------
LAST_FILES=0
LAST_JARS=0

is_complete() {
  local dest="$ROOT/$1/$2"
  [[ -d $dest ]] && [[ -n $(ls -A -- "$dest" 2>/dev/null) ]]
}

has_jar() {
  [[ -n $(find "$1" -type f -iname '*.jar' -print -quit 2>/dev/null) ]]
}

fetch_case() {
  local owner=$1 repo=$2 ref=$3 project=$4 commit=$5
  local rel="$project/$commit"
  local dest="$ROOT/$project/$commit"
  local dir=${remotes_ready[$owner/$repo/$ref]:-}

  LAST_FILES=0; LAST_JARS=0

  if [[ $DRY_RUN -eq 1 ]]; then
    log "  [dry-run] https://github.com/$owner/$repo/tree/$ref/$rel -> $dest/"
    return 0
  fi

  [[ -n $dir ]] || { err "clone de $owner/$repo não preparado"; return 1; }

  # o caminho precisa existir nesta revisão do repositório
  if ! git -C "$dir" cat-file -e "refs/heads/$ref:$rel" 2>/dev/null; then
    err "não encontrado em $owner/$repo@$ref: $rel"
    return 1
  fi

  # quantos .jar este cenário tem (usado no resumo e na retomada)
  local jar_count=0
  jar_count=$(git -C "$dir" ls-tree -r --name-only "refs/heads/$ref" -- "$rel" 2>/dev/null | grep -ci '\.jar$')
  jar_count=${jar_count:-0}
  LAST_JARS=$jar_count

  # retomada: cenário já baixado?
  if [[ $FORCE -eq 0 ]] && is_complete "$project" "$commit"; then
    if ((FULL == 0)); then
      return 3                       # cópia anterior (com ou sem .jar) serve
    fi
    # --full só pula se o cenário não tem .jar ou se eles já foram baixados
    if ((jar_count == 0)) || has_jar "$dest"; then
      return 3
    fi
  fi

  # --force: descarta a cópia anterior para não misturar arquivos obsoletos
  if [[ $FORCE -eq 1 && -d $dest ]]; then
    case $dest in
      "$ROOT"/*/*) rm -rf -- "$dest" || { err "não consigo apagar $dest"; return 1; } ;;
    esac
  fi

  # materializa só esta pasta na árvore de trabalho do clone; no modo padrão
  # os .jar ficam de fora do sparse-checkout (não são nem baixados)
  local patterns=("/$rel/")
  ((FULL == 0)) && patterns+=("!*.jar" "!*.JAR")
  git -C "$dir" sparse-checkout set --no-cone "${patterns[@]}" >/dev/null 2>&1
  if ! git -C "$dir" read-tree -mu HEAD 2>/dev/null; then
    err "falha ao materializar $rel"
    return 1
  fi
  if [[ ! -d $dir/$rel ]]; then
    err "pasta vazia/inacessível em $owner/$repo@$ref: $rel"
    return 1
  fi

  # copia o conteúdo para <ROOT>/<projeto>/<commit>
  mkdir -p "$dest" || return 1
  if ! cp -a -- "$dir/$rel/." "$dest/"; then
    err "falha ao copiar $rel -> $dest"
    return 1
  fi

  # garantia extra no modo padrão: nenhum .jar no destino
  if ((FULL == 0)); then
    find "$dest" -type f -iname '*.jar' -delete 2>/dev/null
  fi

  if [[ -z $(ls -A -- "$dest" 2>/dev/null) ]]; then
    err "cópia vazia para $dest"
    return 1
  fi

  LAST_FILES=$(find "$dest" -type f 2>/dev/null | wc -l)
  return 0
}

# ---------------------------------------------------------------------------
# Loop principal: para cada linha, baixa e volta para a pasta raiz.
# ---------------------------------------------------------------------------
downloaded=0; skipped=0; failed=0; jars_skipped=0
failed_list=()

i=0
while ((i < total)); do
  owner=${owners[i]}; repo=${repos[i]}; ref=${refs[i]}
  project=${projects[i]}; commit=${commits[i]}

  i=$((i + 1))
  log "[$i/$total] $project/$commit"

  # retomada: no modo padrão, se já foi baixado pula sem nem preparar o clone
  # (no --full é preciso o clone para saber se o cenário tem .jar)
  if [[ $DRY_RUN -eq 0 && $FORCE -eq 0 && $FULL -eq 0 ]] && is_complete "$project" "$commit"; then
    log "  já existe, ignorado (use --force para rebaixar)"
    skipped=$((skipped + 1))
    cd "$ROOT" || die "não consigo voltar para $ROOT"
    continue
  fi

  key="$owner/$repo/$ref"
  if [[ -z ${remotes_ready[$key]:-} ]]; then
    if ! prepare_remote "$owner" "$repo" "$ref"; then
      err "não foi possível preparar o clone de $owner/$repo@$ref"
      failed=$((failed + 1)); failed_list+=("${urls[i-1]}")
      continue
    fi
  fi

  fetch_case "$owner" "$repo" "$ref" "$project" "$commit"
  case $? in
    0) downloaded=$((downloaded + 1))
       if [[ $DRY_RUN -eq 0 ]]; then
         if ((FULL == 0 && LAST_JARS > 0)); then
           log "  ok -> $ROOT/$project/$commit/ ($LAST_FILES arquivo(s), $LAST_JARS .jar ignorado(s))"
           jars_skipped=$((jars_skipped + LAST_JARS))
         else
           log "  ok -> $ROOT/$project/$commit/ ($LAST_FILES arquivo(s))"
         fi
       fi ;;
    3) skipped=$((skipped + 1))
       log "  já existe, ignorado (use --force para rebaixar)" ;;
    *) failed=$((failed + 1)); failed_list+=("${urls[i-1]}"); log "  falhou" ;;
  esac

  cd "$ROOT" || die "não consigo voltar para $ROOT"   # volta para a pasta raiz
done

# ---------------------------------------------------------------------------
# Resumo
# ---------------------------------------------------------------------------
log
log "resumo: $downloaded baixado(s), $skipped já existente(s), $failed falha(s)"
if ((FULL == 0 && jars_skipped > 0)); then
  log "        $jars_skipped arquivo(s) .jar ignorado(s) — use --full para baixá-los"
fi
if ((${#failed_list[@]})); then
  log "falhas:"
  printf '  %s\n' "${failed_list[@]}"
  exit 1
fi
exit 0
