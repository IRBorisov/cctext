''' Parsing russian language based on pymorphy3 library. '''
from __future__ import annotations
from typing import Optional

from razdel.substring import Substring as Segment
from pymorphy3.analyzer import Parse as WordParse

from .syntax import RuSyntax, Capitalization
from .rumodel import SemanticRole, Morphology, WordTag, morpho, Grammemes

INDEX_NONE = -1
NO_COORDINATION = -1
WORD_NONE = -1


class WordToken:
    ''' Atomic text token. '''
    def __init__(self, segment: Segment, parse: list[WordParse], main_parse: int = 0):
        self.segment: Segment = segment
        self.forms: list[WordParse] = parse
        self.main: int = main_parse

    def get_morpho(self) -> Morphology:
        ''' Return morphology for current token. '''
        return Morphology(self.get_parse().tag)

    def get_parse(self) -> WordParse:
        ''' Access main form. '''
        return self.forms[self.main]

    def inflect(self, inflection_grams: set[str]) -> Optional[WordParse]:
        ''' Apply inflection to segment text. Does not modify forms '''
        inflected = self.get_parse().inflect(inflection_grams)
        if not inflected:
            return None
        self.segment.text = Capitalization.from_text(self.segment.text).apply_to(inflected.word)
        return inflected


class Collation:
    ''' Parsed data for input coordinated text. '''
    def __init__(self, text: str):
        self.text = text
        self.words: list[WordToken] = []
        self.coordination: list[int] = []
        self.main_word: int = WORD_NONE

    def is_valid(self) -> bool:
        ''' Check if data is parsed correctly '''
        return self.main_word != WORD_NONE

    def get_form(self) -> WordParse:
        ''' Access WordParse. '''
        return self.words[self.main_word].get_parse()

    def get_morpho(self) -> Morphology:
        ''' Access parsed main morphology. '''
        return self.words[self.main_word].get_morpho()

    def add_word(self, segment, forms: list, main_form: int, need_coordination: bool = True):
        ''' Add word information. '''
        self.words.append(WordToken(segment, forms, main_form))
        self.coordination.append(NO_COORDINATION if not need_coordination else 0)

    def inflect(self, target_grams: Grammemes) -> str:
        ''' Inflect text to match required tags. '''
        if self.is_valid():
            origin = self.get_morpho()
            if not origin.tag.grammemes.issuperset(target_grams):
                if self._apply_inflection(origin, target_grams):
                    return self._generate_text()
        return self.text

    def inflect_like(self, base_model: Collation) -> str:
        ''' Create inflection to substitute base_model form. '''
        if self.is_valid():
            morph = base_model.get_morpho()
            if morph.effective_POS:
                tags = set()
                tags.add(morph.effective_POS)
                tags = morph.complete_grams(tags)
                return self.inflect(tags)
        return self.text

    def inflect_dependant(self, master_model: Collation) -> str:
        ''' Create inflection to coordinate with master_model form. '''
        assert self.is_valid()
        morph = master_model.get_morpho()
        tags = morph.coordination_grams()
        tags = self.get_morpho().complete_grams(tags)
        return self.inflect(tags)

    def normal_form(self) -> str:
        ''' Generate normal form. '''
        if self.is_valid():
            main_form = self.get_form()
            new_morpho = Morphology(main_form.normalized.tag)
            new_grams = new_morpho.complete_grams(frozenset())
            return self.inflect(new_grams)
        return self.text

    def _iterate_coordinated(self):
        words_count = len(self.words)
        current_word = self.coordination[words_count]
        while current_word != words_count:
            yield self.words[current_word]
            current_word += self.coordination[current_word]

    def _inflect_main_word(self, origin: Morphology, target_grams: Grammemes) -> Optional[Morphology]:
        full_grams = origin.complete_grams(target_grams)
        inflected = self.words[self.main_word].inflect(full_grams)
        if not inflected:
            return None
        return Morphology(inflected.tag)

    def _apply_inflection(self, origin: Morphology, target_grams: Grammemes) -> bool:
        new_moprho = self._inflect_main_word(origin, target_grams)
        if not new_moprho:
            return False
        inflection_grams = new_moprho.coordination_grams()
        if len(inflection_grams) == 0:
            return True
        for word in self._iterate_coordinated():
            word.inflect(inflection_grams)
        return True

    def _generate_text(self) -> str:
        current_pos = 0
        result = ''
        for token in self.words:
            if token.segment.start > current_pos:
                result += self.text[current_pos: token.segment.start]
            result += token.segment.text
            current_pos = token.segment.stop
        if current_pos + 1 < len(self.text):
            result += self.text[current_pos:]
        return result


class PhraseParser:
    ''' Russian grammar parser. '''
    def __init__(self):
        pass

    def __del__(self):
        pass

    _FILTER_SCORE = 0.005
    _SINGLE_SCORE_SEARCH = 0.2
    _PRIORITY_NONE = NO_COORDINATION

    _MAIN_WAIT_LIMIT = 10  # count words until fixing main
    _MAIN_MAX_FOLLOWERS = 3  # count words after main as coordination candidates

    def parse(self, text: str,
              require_index: int = INDEX_NONE,
              require_grams: Optional[Grammemes] = None) -> Optional[Collation]:
        '''
        Determine morpho tags for input text.
        ::returns:: Morphology of a text or None if no suitable form is available
        '''
        segments = list(RuSyntax.tokenize(text))
        if len(segments) == 0:
            return None
        elif len(segments) == 1:
            return self._parse_single(segments[0], require_index, require_grams)
        else:
            return self._parse_multiword(text, segments, require_index, require_grams)

    def normalize(self, text: str):
        ''' Get normal form for target text. '''
        processed = self.parse(text)
        if processed:
            return processed.normal_form()
        return text

    def find_substr(self, text: str, sub: str) -> tuple[int, int]:
        ''' Search for substring position in text regardless of morphology. '''
        if not text or not sub:
            return (0, 0)
        query = [self.normalize(elem.text) for elem in RuSyntax.tokenize(sub)]
        query_len = len(query)
        start = 0
        current_index = 0
        for token in RuSyntax.tokenize(text):
            text_word = self.normalize(token.text)
            if text_word != query[current_index]:
                current_index = 0
            else:
                if current_index == 0:
                    start = token.start
                current_index += 1
                if current_index == query_len:
                    return (start, token.stop)
        return (0, 0)

    def inflect_context(self, text: str, before: str = '', after: str = '') -> str:
        ''' Inflect text in accordance to context before and after. '''
        target = self.parse(text)
        if not target:
            return text
        target_morpho = target.get_morpho()
        if not target_morpho or not target_morpho.can_coordinate:
            return text

        model_after = self.parse(after)
        model_before = self.parse(before)
        etalon = PhraseParser._choose_context_etalon(target_morpho, model_before, model_after)
        if not etalon:
            return text
        etalon_moprho = etalon.get_morpho()
        if not etalon_moprho.can_coordinate:
            return text

        new_form = PhraseParser._combine_morpho(target_morpho, etalon_moprho.tag)
        return target.inflect(new_form)

    def inflect_substitute(self, substitute_normal: str, original: str) -> str:
        ''' Inflect substitute to match original form. '''
        original_model = self.parse(original)
        if not original_model:
            return substitute_normal
        substitute_model = self.parse(substitute_normal)
        if not substitute_model:
            return substitute_normal
        return substitute_model.inflect_like(original_model)

    def inflect_dependant(self, dependant_normal: str, master: str) -> str:
        ''' Inflect dependant to coordinate with master text. '''
        master_model = self.parse(master)
        if not master_model:
            return dependant_normal
        dependant_model = self.parse(dependant_normal)
        if not dependant_model:
            return dependant_normal
        return dependant_model.inflect_dependant(master_model)

    def _parse_single(self, segment, require_index: int, require_grams: Optional[Grammemes]) -> Optional[Collation]:
        forms = list(self._filtered_parse(segment.text))
        parse_index = INDEX_NONE
        if len(forms) == 0 or require_index >= len(forms):
            return None

        if require_index != INDEX_NONE:
            tags = forms[require_index].tag
            if require_grams and not tags.grammemes.issuperset(require_grams):
                return None
            parse_index = require_index
        else:
            current_score = 0
            for (index, form) in enumerate(forms):
                if not require_grams or form.tag.grammemes.issuperset(require_grams):
                    if form.tag.case == 'nomn':
                        parse_index = index
                        break
                    elif parse_index == INDEX_NONE:
                        current_score = form.score
                        parse_index = index
                    elif form.score / current_score < self._SINGLE_SCORE_SEARCH:
                        break

        if parse_index == INDEX_NONE:
            return None
        result = Collation(segment.text)
        result.add_word(segment, [forms[parse_index]], main_form=0, need_coordination=False)
        result.coordination.append(len(result.words))
        result.main_word = 0
        return result

    def _parse_multiword(self, text: str, segments: list, require_index: int,
                         require_grams: Optional[Grammemes]) -> Optional[Collation]:
        result = Collation(text)
        priority_main: float = self._PRIORITY_NONE
        segment_index = 0
        main_wait = 0
        word_index = 0
        for segment in segments:
            if main_wait > PhraseParser._MAIN_WAIT_LIMIT:
                break
            segment_index += 1
            priority = self._parse_segment(result, segment, require_index, require_grams)
            if priority is None:
                continue  # skip non-parsable entities
            main_wait += 1
            if priority > priority_main:
                result.main_word = word_index
                priority_main = priority
            word_index += 1
        if result.main_word == INDEX_NONE:
            return None
        self._finalize_coordination(result)
        if segment_index < len(segments):
            pass  # finish to parse segments after main if needed
        return result

    def _parse_segment(self,
                       output: Collation,
                       segment: Segment,
                       require_index: int,
                       require_grams: Optional[Grammemes]) -> Optional[float]:
        ''' Return priority for this can be a new main word '''
        forms = list(self._filtered_parse(segment.text))
        if len(forms) == 0:
            return None
        main_index: int = INDEX_NONE
        segment_score: float = self._PRIORITY_NONE
        needs_coordination = False
        local_sum: float = 0
        score_sum: float = 0
        if require_index != INDEX_NONE:
            form = forms[require_index]
            if not require_grams or form.tag.grammemes.issuperset(require_grams):
                (local_max, segment_score) = PhraseParser._get_priorities_for(form.tag)
                main_index = require_index
                needs_coordination = Morphology.is_dependable(form.tag.POS)
        else:
            local_max = self._PRIORITY_NONE
            for (index, form) in enumerate(forms):
                if require_grams and not form.tag.grammemes.issuperset(require_grams):
                    continue
                (local_priority, global_priority) = PhraseParser._get_priorities_for(form.tag)
                needs_coordination = needs_coordination or Morphology.is_dependable(form.tag.POS)
                local_sum += global_priority * form.score
                score_sum += form.score
                if local_priority > local_max:
                    local_max = local_priority
                    # segment_score = global_priority
                    main_index = index
        if score_sum == 0:
            return None
        segment_score = local_sum / score_sum
        output.add_word(segment, forms, main_index, needs_coordination)
        return segment_score
        # Alternative: return segment_score
        # penalty_suspicious = 0 if local_max == 0 else (1 - local_sum / local_max) * self._PRIORITY_PENALTY
        # return segment_score - penalty_suspicious

    @classmethod
    def _finalize_coordination(cls, target: Collation):
        main_morpho: Morphology = target.get_morpho()
        main_coordinate = main_morpho.can_coordinate
        target.coordination[target.main_word] = NO_COORDINATION
        first_change = INDEX_NONE
        current_len = 0
        for (index, word) in enumerate(target.words):
            if target.coordination[index] == NO_COORDINATION or index - target.main_word > cls._MAIN_MAX_FOLLOWERS:
                needs_change = False
                if index != target.main_word:
                    word.main = INDEX_NONE
            else:
                word.main = PhraseParser._find_coordination(word.forms, main_morpho.tag, index < target.main_word)
                needs_change = word.main != INDEX_NONE
                if not needs_change or not main_coordinate:
                    target.coordination[index] = NO_COORDINATION
            current_len += 1
            if needs_change and main_coordinate:
                target.coordination[index] = current_len
                current_len = 0
                if first_change == INDEX_NONE:
                    first_change = index
        if first_change == INDEX_NONE:
            target.coordination.append(len(target.words))
            return
        previous_reference = first_change
        current_word = len(target.words)
        target.coordination.append(current_len + 1)
        while target.coordination[current_word] != INDEX_NONE:
            previous_word = current_word - target.coordination[current_word]
            target.coordination[current_word] = previous_reference
            previous_reference = current_word - previous_word
            current_word = previous_word
            if previous_reference == 0 or current_word < 0:
                break

    @staticmethod
    def _find_coordination(forms: list, main_tag: WordTag, before_main: bool) -> int:
        for (index, form) in enumerate(forms):
            pos = form.tag.POS
            case = form.tag.case
            if pos not in ['ADJF', 'ADJS', 'PRTF', 'PRTS']:
                continue
            if SemanticRole.from_POS(pos) == SemanticRole.term and case == 'gent':
                if before_main:
                    continue
                else:
                    return INDEX_NONE
            if case == main_tag.case:
                return index
            elif main_tag.case in ['accs', 'gent'] and case in ['accs', 'gent']:
                return index
        return INDEX_NONE

    @staticmethod
    def _filtered_parse(text: str):
        capital = Capitalization.from_text(text)
        score_filter = PhraseParser._filter_score(morpho.parse(text))
        yield from PhraseParser._filter_capital(score_filter, capital)

    @staticmethod
    def _filter_score(generator):
        for form in generator:
            if form.score < PhraseParser._FILTER_SCORE:
                break
            yield form

    @staticmethod
    def _filter_capital(generator, capital: Capitalization):
        if capital in [Capitalization.upper_case, Capitalization.mixed]:
            for form in generator:
                if 'Abbr' not in form.tag.grammemes:
                    continue
                yield form
        else:
            yield from generator

    @staticmethod
    def _parse_word(text: str, require_index: int = INDEX_NONE,
                    require_grams: Optional[Grammemes] = None) -> Optional[Morphology]:
        parsed_variants = morpho.parse(text)
        if not parsed_variants or require_index >= len(parsed_variants):
            return None
        if require_index != INDEX_NONE:
            tags = parsed_variants[require_index].tag
            if not require_grams or tags.grammemes.issuperset(require_grams):
                return Morphology(tags)
            else:
                return None
        else:
            for variant in parsed_variants:
                tags = variant.tag
                if not require_grams or tags.grammemes.issuperset(require_grams):
                    return Morphology(tags)
        return None

    @staticmethod
    def _get_priorities_for(tag: WordTag) -> tuple[float, float]:
        ''' Return pair of local and global priorities. '''
        if tag.POS in ['VERB', 'INFN']:
            return (9, 10)
        if tag.POS in ['NOUN', 'NPRO']:
            return (10, 9) if 'nomn' in tag.grammemes and 'Fixd' not in tag.grammemes else (8, 8)
        if tag.POS in ['PRTF', 'PRTS']:
            return (6, 6)
        if tag.POS in ['ADJF', 'ADJS']:
            return (5, 5)
        if tag.POS == 'ADVB':
            return (7, 4)
        return (0, 0)

    @staticmethod
    def _choose_context_etalon(target: Morphology,
                               before: Optional[Collation],
                               after: Optional[Collation]) -> Optional[Collation]:
        if not before or not before.get_morpho().can_coordinate:
            return after
        if not after or not after.get_morpho().can_coordinate:
            return before

        before_semantic = before.get_morpho().semantic
        after_semantic = after.get_morpho().semantic
        if target.semantic == SemanticRole.definition:
            if after_semantic == SemanticRole.term:
                return after
            if before_semantic == SemanticRole.term:
                return before
            if before_semantic == SemanticRole.definition:
                return before
            return after

        if target.semantic == SemanticRole.term:
            if before_semantic == SemanticRole.definition:
                return before
            if after_semantic == SemanticRole.definition:
                return after

        return before

    @staticmethod
    def _combine_morpho(target: Morphology, etalon: WordTag) -> frozenset[str]:
        part_of_speech = target.tag.POS
        number = etalon.number
        if number == 'plur':
            return frozenset([part_of_speech, number, etalon.case])
        else:
            gender = etalon.gender if target.semantic != SemanticRole.term else target.tag.gender
            return frozenset([part_of_speech, number, gender, etalon.case])
