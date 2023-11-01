from dataclasses import dataclass


@dataclass
class Token:
    bearer_token: str
    expiration: float
    main_id: str
