
from bot.database.models import (
    Base,
    Tutor,
    Client,
    LeadSource,
    Assignment,
    Payment,
    AssignmentFinance,
)

print("Models imported successfully!")

print("\nRegistered tables:")
for table in Base.metadata.sorted_tables:
    print(f"- {table.name}")

print("\nModels check completed!")
