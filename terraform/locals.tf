locals {
  ###################################
  # 1) Process the entire config file
  ###################################
  
  # Read the config file as a raw string
  raw_yaml = file("${path.module}/../config.yaml")

  # Parse it once so we can get project ID and use_free_tier
  config_parsed_for_id = yamldecode(local.raw_yaml)

  # Decide tier
  use_free_tier2 = try(local.config_parsed_for_id.project.use_free_tier, false)
  tier_string    = local.use_free_tier2 ? "free_tier" : "standard"

  # Replace %PROJECT_ID% and %PROJECT_TIER% in the raw YAML
  replaced_yaml = replace(
    replace(
      local.raw_yaml,
      "%PROJECT_ID%",
      local.config_parsed_for_id.project.id
    ),
    "%PROJECT_TIER%",
    local.tier_string
  )

  # Finally decode the replaced YAML into a fully processed config object
  config = yamldecode(local.replaced_yaml)

  ################################################################
  # 2) Create processed_env_vars based on config.cloud_function.environment_variables
  ################################################################

  # If your environment variables still contain %PROJECT_ID% or %PROJECT_TIER%
  # placeholders, you can replace them here. This example re-replaces them 
  # individually in each environment variable, in case the above wasn't enough.

  processed_env_vars = {
    for key, value in local.config.cloud_function.environment_variables :
    key => replace(
      replace(
        value,
        "%PROJECT_ID%",
        local.config.project.id
      ),
      "%PROJECT_TIER%",
      local.tier_string
    )
  }

  ###################################
}

