"""Eccezioni del dominio: separano i problemi *nostri* da quelli *dei dati*."""


class MtgSocialError(Exception):
    """Errore generico dell'agente."""


class ConfigError(MtgSocialError):
    """Configurazione mancante o incoerente."""


class SourceError(MtgSocialError):
    """La sorgente dati non risponde o risponde in un formato inatteso."""


class NoDataError(MtgSocialError):
    """La sorgente ha risposto ma non ci sono dati per il periodo richiesto.

    Non e' un bug: e' la condizione normale di "questa settimana non si gioca".
    Le pipeline la trattano come skip pulito, non come fallimento.
    """


class RenderError(MtgSocialError):
    """Il rendering HTML -> PNG e' fallito."""


class PublishError(MtgSocialError):
    """La pubblicazione su Instagram e' fallita.

    `code` e `subcode` sono quelli di Meta, quando la risposta li porta: senza
    di loro l'unico modo di distinguere un errore su cui vale la pena
    riprovare da uno definitivo sarebbe leggere il messaggio, che Meta cambia
    quando gli pare.
    """

    def __init__(self, message: str, *, code: int | None = None,
                 subcode: int | None = None):
        super().__init__(message)
        self.code = code
        self.subcode = subcode
