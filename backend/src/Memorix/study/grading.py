"""Apresentação sem gabarito e correção de questionários previamente validados."""


OBJECTIVE_TYPES = ("multipla_escolha", "verdadeiro_falso")


def _questionnaire(snapshot: dict) -> tuple[str, list[dict]]:
    kind = snapshot.get("kind")
    items = snapshot.get("items")
    if kind not in OBJECTIVE_TYPES:
        raise ValueError("O estudo com correção objetiva aceita apenas múltipla escolha e V/F.")
    if not isinstance(items, list) or not items:
        raise ValueError("O questionário deve conter questões.")
    return kind, items


def present_questions(snapshot: dict) -> list[dict]:
    """Retorna somente os campos que o aluno pode ver antes de responder."""
    kind, items = _questionnaire(snapshot)
    questions = []
    for index, item in enumerate(items):
        question = {"item_index": index, "question": item["question"]}
        if kind == "multipla_escolha":
            question["options"] = list(item["options"])
        questions.append(question)
    return questions


def grade_answers(snapshot: dict, answers: object) -> dict:
    """Corrige a lista completa; bool não é aceito como índice e int não é V/F."""
    kind, items = _questionnaire(snapshot)
    if not isinstance(answers, list) or len(answers) != len(items):
        raise ValueError("Envie uma lista com exatamente uma resposta por questão, na ordem apresentada.")
    feedback = []
    correct_count = 0
    for index, (item, answer) in enumerate(zip(items, answers)):
        if kind == "multipla_escolha":
            if type(answer) is not int or not 0 <= answer < len(item["options"]):
                raise ValueError(f"Resposta da questão {index}: esperado índice inteiro de 0 a 3.")
            expected = item["answer_index"]
        else:
            if type(answer) is not bool:
                raise ValueError(f"Resposta da questão {index}: esperado booleano true ou false.")
            expected = item["answer"]
        correct = answer == expected
        correct_count += int(correct)
        result = {
            "item_index": index,
            "question": item["question"],
            "answer": answer,
            "expected_answer": expected,
            "correct": correct,
            "explanation": item["explanation"],
            "citations": item["citations"],
        }
        if kind == "multipla_escolha":
            result["options"] = list(item["options"])
        feedback.append(result)
    return {
        "total_count": len(items),
        "correct_count": correct_count,
        "accuracy": correct_count / len(items),
        "items": feedback,
    }
