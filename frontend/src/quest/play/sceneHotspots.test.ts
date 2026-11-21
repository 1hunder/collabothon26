import { describe, expect, it } from 'vitest';
import { coverRect, sceneHotspots } from './sceneHotspots';

const rectOf = (key: string) => {
  const cfg = sceneHotspots[key];
  const h = cfg?.hotspots[0];
  if (!cfg || !h) throw new Error(`no hotspot for ${key}`);
  return { natural: cfg.natural, rect: h.rect };
};

describe('coverRect (object-fit: cover, centred)', () => {
  it('library at 430x932: height fills, the sides are cropped', () => {
    const { natural, rect } = rectOf('library');
    const r = coverRect({ width: 430, height: 932 }, natural, rect);
    expect(r.left).toBeCloseTo(0, 1);
    expect(r.width).toBeCloseTo(162.5, 0);
    expect(r.top).toBeCloseTo(55.9, 0);
    expect(r.height).toBeCloseTo(372.8, 0);
  });

  it('library at 360x740', () => {
    const { natural, rect } = rectOf('library');
    const r = coverRect({ width: 360, height: 740 }, natural, rect);
    expect(r.left).toBeCloseTo(0, 1);
    expect(r.width).toBeCloseTo(138.3, 0);
    expect(r.top).toBeCloseTo(44.4, 0);
    expect(r.height).toBeCloseTo(296, 0);
  });

  it('the tavern has no hotspot: the notice board was removed', () => {
    expect(sceneHotspots.tavern).toBeUndefined();
  });

  it('market stall at 430x932 starts at the left edge', () => {
    const { natural, rect } = rectOf('market_square');
    const r = coverRect({ width: 430, height: 932 }, natural, rect);
    expect(r.left).toBe(0);
    expect(r.top).toBeCloseTo(205, 0);
    expect(r.height).toBeCloseTo(428.7, 0);
  });

  it('a wide box crops top and bottom and clamps the rect to the box', () => {
    const { natural, rect } = rectOf('market_square');
    const r = coverRect({ width: 1000, height: 500 }, natural, rect);
    expect(r.top).toBe(0);
    expect(r.top + r.height).toBeLessThanOrEqual(500);
    expect(r.left + r.width).toBeLessThanOrEqual(1000);
  });
});
