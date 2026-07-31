import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import PhotoGallery from './PhotoGallery';
import { api } from '../api.js';

vi.mock('./Toast.jsx', () => ({ useToast: () => vi.fn() }));

vi.mock('../api.js', () => ({
  api: {
    photoUrl: (id) => `/api/photos/${id}/file`,
    setCover: vi.fn().mockResolvedValue(undefined),
    updateCoverFrame: vi.fn().mockResolvedValue({ cover_focal_x: 0.5, cover_focal_y: 0.5, cover_zoom: 1 }),
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

/** Stub the frame box's measured size — must be installed before the frame mounts. */
function mockFrameRect() {
  return vi.spyOn(Element.prototype, 'getBoundingClientRect').mockReturnValue({ width: 480, height: 270 });
}

/** Simulate the cover-framer's image finishing load with a 16:9 natural size matching the frame. */
function loadFramerImage() {
  const img = screen.getByAltText('Frame the cover crop');
  Object.defineProperty(img, 'naturalWidth', { value: 480, configurable: true });
  Object.defineProperty(img, 'naturalHeight', { value: 270, configurable: true });
  fireEvent.load(img);
}

describe('PhotoGallery cover photo', () => {
  it('marks only the cover photo with a glyph', () => {
    renderGallery();
    expect(screen.getAllByTitle('Cover photo')).toHaveLength(1);
  });

  it('offers "Set as cover" on a non-cover photo and calls the API, closing the lightbox', async () => {
    const onChange = vi.fn();
    const { container } = renderGallery({ onChange });
    await userEvent.click(screen.getByAltText('side.png')); // open photo 2 (not the cover)
    await userEvent.click(screen.getByText('Set as cover'));
    expect(api.setCover).toHaveBeenCalledWith(2);
    expect(onChange).toHaveBeenCalled();
    expect(container.querySelector('.lightbox')).not.toBeInTheDocument();
  });

  it('offers "Edit cover ★" instead of "Set as cover" on the current cover photo', async () => {
    renderGallery();
    await userEvent.click(screen.getByAltText('Front')); // open photo 1 (the cover)
    expect(screen.queryByText('Set as cover')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Edit cover ★/ })).toBeInTheDocument();
    expect(screen.getByText('Delete')).toBeInTheDocument(); // other actions still present
  });

  it('hides "Set as cover" for read-only members', async () => {
    renderGallery({ ro: true });
    await userEvent.click(screen.getByAltText('side.png'));
    expect(screen.queryByText('Set as cover')).not.toBeInTheDocument();
  });
});

describe('PhotoGallery lightbox navigation', () => {
  it('shows a counter and wraps around with the nav arrows', async () => {
    renderGallery();
    await userEvent.click(screen.getByAltText('Front'));
    expect(screen.getByText('1 / 2')).toBeInTheDocument();

    await userEvent.click(screen.getByLabelText('Next photo'));
    expect(screen.getByText('2 / 2')).toBeInTheDocument();

    await userEvent.click(screen.getByLabelText('Next photo')); // wraps past the last photo
    expect(screen.getByText('1 / 2')).toBeInTheDocument();

    await userEvent.click(screen.getByLabelText('Previous photo')); // wraps before the first
    expect(screen.getByText('2 / 2')).toBeInTheDocument();
  });

  it('navigates with the left/right arrow keys, wrapping at the ends', async () => {
    renderGallery();
    await userEvent.click(screen.getByAltText('Front'));
    fireEvent.keyDown(document, { key: 'ArrowRight' });
    expect(screen.getByText('2 / 2')).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'ArrowRight' });
    expect(screen.getByText('1 / 2')).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'ArrowLeft' });
    expect(screen.getByText('2 / 2')).toBeInTheDocument();
  });

  it('hides the nav arrows with only one photo', async () => {
    render(<PhotoGallery photos={[photos[0]]} vehicleId={7} coverPhotoId={1} onChange={vi.fn()} />);
    await userEvent.click(screen.getByAltText('Front'));
    expect(screen.getByText('1 / 1')).toBeInTheDocument();
    expect(screen.queryByLabelText('Next photo')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Previous photo')).not.toBeInTheDocument();
  });
});

describe('PhotoGallery Escape handling', () => {
  it('closes the lightbox on Escape', async () => {
    renderGallery();
    await userEvent.click(screen.getByAltText('Front'));
    expect(screen.getByText('1 / 2')).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByText('1 / 2')).not.toBeInTheDocument();
  });

  it('exits the cover-framing editor on Escape before closing the whole lightbox', async () => {
    renderGallery();
    await userEvent.click(screen.getByAltText('Front'));
    await userEvent.click(screen.getByRole('button', { name: /Edit cover/ }));
    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });
    // Back to the plain lightbox view, still open.
    expect(screen.getByText('1 / 2')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByText('1 / 2')).not.toBeInTheDocument();
  });
});

describe('PhotoGallery cover framing', () => {
  it('opens the pan/zoom editor and saves the resulting frame', async () => {
    const rectSpy = mockFrameRect(); // must be in place before the frame box mounts
    renderGallery();
    await userEvent.click(screen.getByAltText('Front'));
    await userEvent.click(screen.getByRole('button', { name: /Edit cover/ }));

    const saveButton = screen.getByRole('button', { name: 'Save' });
    expect(saveButton).toBeDisabled(); // waiting on image load + frame measurement

    loadFramerImage();
    expect(saveButton).not.toBeDisabled();

    await userEvent.click(saveButton);
    expect(api.updateCoverFrame).toHaveBeenCalledWith(1, {
      focal_x: 0.5, focal_y: 0.5, zoom: 1,
    });
    // Back to the plain lightbox view after saving.
    expect(screen.getByText('1 / 2')).toBeInTheDocument();
    rectSpy.mockRestore();
  });

  it('discards changes on Cancel without calling the API', async () => {
    const rectSpy = mockFrameRect();
    renderGallery();
    await userEvent.click(screen.getByAltText('Front'));
    await userEvent.click(screen.getByRole('button', { name: /Edit cover/ }));
    loadFramerImage();

    await userEvent.click(screen.getByText('Cancel'));
    expect(api.updateCoverFrame).not.toHaveBeenCalled();
    expect(screen.getByText('1 / 2')).toBeInTheDocument();
    rectSpy.mockRestore();
  });
});
