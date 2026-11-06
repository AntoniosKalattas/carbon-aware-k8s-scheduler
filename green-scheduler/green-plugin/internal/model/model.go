// Package model implements a synthetic, fixed-work energy model.
package model

import (
	"fmt"
	"math"
)

type Profile struct {
	Watts  float64 `json:"watts"`
	Carbon float64 `json:"carbon"`
}

type Config struct {
	Mode    string             `json:"mode"`
	Seconds float64            `json:"seconds"`
	Regions map[string]Profile `json:"regions"`
}

func positive(x float64) bool { return x > 0 && !math.IsNaN(x) && !math.IsInf(x, 0) }
func (c Config) Validate() error {
	if c.Mode != "energy" && c.Mode != "carbon" {
		return fmt.Errorf("mode must be energy or carbon")
	}
	if !positive(c.Seconds) || len(c.Regions) == 0 {
		return fmt.Errorf("positive runtime and regions required")
	}
	for region, p := range c.Regions {
		if region == "" || !positive(p.Watts) || p.Carbon < 0 || math.IsNaN(p.Carbon) || math.IsInf(p.Carbon, 0) {
			return fmt.Errorf("invalid profile for %q", region)
		}
		if math.IsInf(c.Cost(p), 0) {
			return fmt.Errorf("cost overflows for %q", region)
		}
	}
	return nil
}

func (c Config) Cost(p Profile) float64 {
	energy := p.Watts * c.Seconds / 3600000
	if c.Mode == "energy" {
		return energy
	}
	return energy * p.Carbon
}

// Score maps configured costs to 0..100, with the lowest cost receiving 100.
// Missing region data receives 0, allowing feasible fallback placement.
func (c Config) Score(region string) int64 {
	p, ok := c.Regions[region]
	if !ok {
		return 0
	}
	lo, hi := math.Inf(1), math.Inf(-1)
	for _, profile := range c.Regions {
		cost := c.Cost(profile)
		lo = math.Min(lo, cost)
		hi = math.Max(hi, cost)
	}
	if hi == lo {
		return 100
	}
	return int64(math.Round(100 * (hi - c.Cost(p)) / (hi - lo)))
}
