from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from pathlib import Path


EPSILON = "ε"
EOF = "EOF"


def _common_prefix(
    first: tuple[str, ...],
    second: tuple[str, ...],
) -> tuple[str, ...]:
    prefix: list[str] = []
    for left, right in zip(first, second):
        if left != right:
            break
        prefix.append(left)
    return tuple(prefix)


@dataclass(frozen=True)
class Production:
    lhs: str
    rhs: tuple[str, ...]

    def __str__(self) -> str:
        symbols = " ".join(self.rhs) if self.rhs else EPSILON
        return f"{self.lhs} ::= {symbols}"


class Grammar:
    def __init__(self, productions: list[Production]):
        if not productions:
            raise ValueError("a gramática deve possuir ao menos uma produção")

        self.start_symbol = productions[0].lhs
        self.nonterminals = list(
            dict.fromkeys(production.lhs for production in productions)
        )
        self._by_lhs: dict[str, list[Production]] = {
            nonterminal: [] for nonterminal in self.nonterminals
        }
        for production in productions:
            self._by_lhs[production.lhs].append(production)

        self.first: dict[str, set[str]] = {}
        self.follow: dict[str, set[str]] = {}
        self.start: dict[Production, set[str]] = {}

    @property
    def productions(self) -> list[Production]:
        return [
            production
            for nonterminal in self.nonterminals
            for production in self._by_lhs[nonterminal]
        ]

    @property
    def terminals(self) -> set[str]:
        nonterminals = set(self.nonterminals)
        return {
            symbol
            for production in self.productions
            for symbol in production.rhs
            if symbol not in nonterminals
        }

    @classmethod
    def from_text(cls, text: str) -> Grammar:
        productions: list[Production] = []

        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "::=" not in line:
                raise ValueError(f"linha {line_number}: esperado '::='")

            lhs, rhs = line.split("::=", 1)
            lhs = lhs.strip()
            if not lhs:
                raise ValueError(f"linha {line_number}: lado esquerdo vazio")

            for alternative in rhs.split("|"):
                alternative = alternative.strip()
                if not alternative:
                    raise ValueError(
                        f"linha {line_number}: alternativa vazia deve usar ε"
                    )
                symbols = tuple(alternative.split())
                if symbols == (EPSILON,):
                    symbols = ()
                elif EPSILON in symbols:
                    raise ValueError(
                        f"linha {line_number}: ε deve ser a alternativa completa"
                    )
                productions.append(Production(lhs, symbols))

        return cls(productions)

    @classmethod
    def from_file(cls, path: str | Path) -> Grammar:
        return cls.from_text(Path(path).read_text(encoding="utf-8"))

    def productions_for(self, nonterminal: str) -> list[Production]:
        return list(self._by_lhs[nonterminal])

    def _empty_sets_by_nonterminal(self) -> dict[str, set[str]]:
        return {nonterminal: set() for nonterminal in self.nonterminals}

    def _invalidate_sets(self) -> None:
        self.first = {}
        self.follow = {}
        self.start = {}

    def _insert_nonterminal_after(self, existing: str, new: str) -> None:
        position = self.nonterminals.index(existing) + 1
        self.nonterminals.insert(position, new)
        self._by_lhs[new] = []

    def _replace_productions(
        self,
        nonterminal: str,
        alternatives: list[tuple[str, ...]],
    ) -> None:
        self._by_lhs[nonterminal] = [
            Production(nonterminal, symbols) for symbols in alternatives
        ]
        self._invalidate_sets()

    def _fresh_nonterminal(self, base: str) -> str:
        candidate = base + "'"
        occupied = set(self.nonterminals) | self.terminals
        while candidate in occupied:
            candidate += "'"
        return candidate

    def first_of_sequence(self, symbols: tuple[str, ...]) -> set[str]:
        """Calcule FIRST para uma sequência de zero ou mais símbolos."""
        # sequencia vazia, portanto first = {}
        if not symbols:
            return {EPSILON}

        f_seq_result: set[str] = set()

        for i, symbol in enumerate(symbols):
            # Se for terminal, first é o terminal
            if symbol not in self.nonterminals:
                f_seq_result.add(symbol)
                break

            # caso contrário, necessário checar o first do não terminal, menos o EPSILON, caso ele exista
            f_symbol = self.first.get(symbol, set())
            f_seq_result.update(f_symbol - {EPSILON})

            # Se nao tiver EPSILON, first acaba aqui
            if EPSILON not in f_symbol:
                break
        else:
            # Se todos as produções são não terminais e anuláveis, first receberá EPSILON
            f_seq_result.add(EPSILON)

        return f_seq_result

    def build_first(self) -> None:
        """Preencha self.first por iteração até um ponto fixo."""
        self.first = self._empty_sets_by_nonterminal()

        alterado = True
        while alterado:
            alterado = False
            for nonterminal in self.nonterminals:
                for prod in self.productions_for(nonterminal):
                    # calcula first a direita da produção
                    first_rhs = self.first_of_sequence(prod.rhs)

                    # verifica se first recebeu algum simbolo novo
                    antes = len(self.first[nonterminal])
                    self.first[nonterminal].update(first_rhs)
                    depois = len(self.first[nonterminal])

                    if depois > antes:
                        alterado = True
        return

    def build_follow(self) -> None:
        """Preencha self.follow; FIRST deve ter sido calculado antes."""
        self.follow = self._empty_sets_by_nonterminal()

        # adiciona EOF ao simbolo inicial, pois ele sempre o terá
        self.follow[self.start_symbol].add(EOF)

        alterado = True
        while alterado:
            alterado = False
            for prod in self.productions:
                a = prod.lhs
                rhs = prod.rhs

                # trailer avança com follow da direita para a esquerda
                trailer = self.follow[a].copy()
                for symbol in reversed(rhs):

                    # se for nao terminal, adiciona o trailer atual no follow do simbolo
                    if symbol in self.nonterminals:
                        antes = len(self.follow[symbol])
                        self.follow[symbol].update(trailer)
                        depois = len(self.follow[symbol])

                        if depois > antes:
                            alterado = True

                        # atualiza trailer para o simbolo a esquerda
                        f_symbol = self.first[symbol]

                        # se simbolo é anulavel (contém EPSILON em first), recebe trailer U (first − EPSILON)
                        if EPSILON in f_symbol:
                            trailer = (f_symbol - {EPSILON}) | trailer
                        else:
                            # trailer vira first
                            trailer = f_symbol
                    else:
                        # se for terminal, recebe o simbolo
                        trailer = {symbol}
        return

    def build_start(self) -> None:
        """Associe a cada produção seu conjunto START."""
        self.start = {}

        for prod in self.productions:
            a = prod.lhs
            bt = prod.rhs
            f_bt = self.first_of_sequence(bt)
            # se EPSILON não pertence ao first de beta, start é o first de beta
            if EPSILON not in f_bt:
                self.start[prod] = f_bt.copy()

            # caso contrario, recebe follow(A) U first(beta) - EPSILON
            else:
                self.start[prod] = (f_bt - {EPSILON}) | self.follow[a]
        return

    def build_sets(self) -> None:
        self.build_first()
        self.build_follow()
        self.build_start()

    def eliminate_direct_left_recursion(self, nonterminal: str) -> bool:
        """Elimine a recursão direta de um não terminal, se existir."""
        producoes = self.productions_for(nonterminal)

        recursao: list[tuple[str, ...]] = []  # Produções 'a', com próprio não terminal a esquerda (ex - A: A a)
        not_recursao: list[tuple[str, ...]] = []  # Produções 'b', sem o próprio não terminal a esquerda (ex - A: b)

        # percorre produções, separando o que é recursivo e oq não é
        for prod in producoes:
            if prod.rhs and prod.rhs[0] == nonterminal:
                recursao.append(prod.rhs[1:])  # guarda apenas a, não A
            else:
                not_recursao.append(prod.rhs)  # guarda b

        # Se nao detectar recursão nas produções, retorna falso
        if not recursao:
            return False

        # Cria a nova produção intermediária A' e o insere logo depois do A na lista
        aux = self._fresh_nonterminal(nonterminal)
        self._insert_nonterminal_after(nonterminal, aux)

        # cria produções com elementos que não tinham recursão (ex - A: b) por (ex - A: b A')
        novas_not_recursao = [nr + (aux,) for nr in not_recursao]
        self._replace_productions(nonterminal, novas_not_recursao)

        # constroi produções sem recursão do A' (ex - A': a A') por (ex - A: b)
        novas_recursao = [r + (aux,) for r in recursao]
        novas_recursao.append(())  # também adiciona produção vazia
        self._replace_productions(aux, novas_recursao)

        return True

    def eliminate_all_direct_left_recursion(self) -> None:
        for nonterminal in list(self.nonterminals):
            self.eliminate_direct_left_recursion(nonterminal)

    def left_factor_once(self, nonterminal: str) -> bool:
        """Infraestrutura fornecida: fatore um prefixo comum."""
        productions = self.productions_for(nonterminal)
        best_prefix: tuple[str, ...] = ()

        for first, second in combinations(productions, 2):
            prefix = _common_prefix(first.rhs, second.rhs)
            if len(prefix) > len(best_prefix):
                best_prefix = prefix

        if not best_prefix:
            return False

        group = [
            production
            for production in productions
            if production.rhs[: len(best_prefix)] == best_prefix
        ]
        helper = self._fresh_nonterminal(nonterminal)
        self._insert_nonterminal_after(nonterminal, helper)

        alternatives: list[tuple[str, ...]] = []
        inserted = False
        for production in productions:
            if production in group:
                if not inserted:
                    alternatives.append(best_prefix + (helper,))
                    inserted = True
            else:
                alternatives.append(production.rhs)

        suffixes = list(
            dict.fromkeys(
                production.rhs[len(best_prefix):]
                for production in group
            )
        )
        self._replace_productions(nonterminal, alternatives)
        self._replace_productions(helper, suffixes)
        return True

    def left_factor(self) -> bool:
        """Infraestrutura fornecida: repita a fatoração até estabilizar."""
        changed_any = False
        while True:
            for nonterminal in list(self.nonterminals):
                if self.left_factor_once(nonterminal):
                    changed_any = True
                    break
            else:
                return changed_any

    def ll1_conflicts(
        self,
    ) -> list[tuple[Production, Production, set[str]]]:
        """Infraestrutura fornecida: encontre STARTs sobrepostos."""
        if set(self.start) != set(self.productions):
            raise RuntimeError("calcule START antes de verificar LL(1)")

        conflicts: list[tuple[Production, Production, set[str]]] = []
        for nonterminal in self.nonterminals:
            for first, second in combinations(
                self.productions_for(nonterminal), 2
            ):
                overlap = self.start[first] & self.start[second]
                if overlap:
                    conflicts.append((first, second, overlap))
        return conflicts

    def is_ll1(self) -> bool:
        return not self.ll1_conflicts()

    @staticmethod
    def _format_set(values: set[str]) -> str:
        return "{ " + ", ".join(sorted(values)) + " }"

    def format_sets(self) -> str:
        lines = ["FIRST"]
        lines.extend(
            f"{nonterminal}: {self._format_set(self.first[nonterminal])}"
            for nonterminal in self.nonterminals
        )
        lines.append("")
        lines.append("FOLLOW")
        lines.extend(
            f"{nonterminal}: {self._format_set(self.follow[nonterminal])}"
            for nonterminal in self.nonterminals
        )
        lines.append("")
        lines.append("START")
        lines.extend(
            f"{production}: {self._format_set(self.start[production])}"
            for production in self.productions
        )
        return "\n".join(lines)

    def __str__(self) -> str:
        lines: list[str] = []
        for nonterminal in self.nonterminals:
            alternatives = " | ".join(
                " ".join(production.rhs) if production.rhs else EPSILON
                for production in self.productions_for(nonterminal)
            )
            lines.append(f"{nonterminal} ::= {alternatives}")
        return "\n".join(lines)
