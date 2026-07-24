import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import PhotoGallery from './PhotoGallery';
import { api } from '../api.js';

vi.mock('./Toast.jsx', () => ({ useToast: () => vi.fn() }));

vi.mock('../api.js', () => ({
  api: {
    photoUrl: (id) => `/api/photos/${id}/file`,
    setCover: vi.fn().mockResolvedValue(undefined),
    deletePhoto: vi.fn(),
    updatePhoto: vi.fn(),
    uploadPhoto: vi.fn(),
  },
}));

const photos = [
  { id: 1, caption: 'Front', original_name: 'front.png', service_title: null, service_log_id: null },
  { id: 2, caption: null, original_name: 'side.png', service_title: null, service_log_id: null },
];

beforeEach(() => vi.clearAllMocks());

function renderGallery(props = {}) {
  return render(
    <PhotoGallery photos={photos} vehicleId={7} coverPhotoId={1} onChange={vi.fn()} {...props} />,
  );
}

describe('PhotoGallery cover photo', () => {
  it('marks only the cover photo with a glyph', () => {
    renderGallery();
    expect(screen.getAllByTitle('Cover photo')).toHaveLength(1);
  });

  it('offers "Set as cover" on a non-cover photo and calls the API', async () => {
    const onChange = vi.fn();
    renderGallery({ onChange });
    await userEvent.click(screen.getByAltText('side.png')); // open photo 2 (not the cover)
    await userEvent.click(screen.getByText('Set as cover'));
    expect(api.setCover).toHaveBeenCalledWith(2);
    expect(onChange).toHaveBeenCalled();
  });

  it('does not offer "Set as cover" on the current cover photo', async () => {
    renderGallery();
    await userEvent.click(screen.getByAltText('Front')); // open photo 1 (the cover)
    expect(screen.queryByText('Set as cover')).not.toBeInTheDocument();
    expect(screen.getByText('Delete')).toBeInTheDocument(); // other actions still present
  });

  it('hides "Set as cover" for read-only members', async () => {
    renderGallery({ ro: true });
    await userEvent.click(screen.getByAltText('side.png'));
    expect(screen.queryByText('Set as cover')).not.toBeInTheDocument();
  });
});
